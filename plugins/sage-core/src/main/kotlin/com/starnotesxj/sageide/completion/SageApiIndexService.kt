package com.starnotesxj.sageide.completion

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.starnotesxj.sagemath.sageapi.SageApiIndexLoader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import java.nio.file.Files
import java.nio.file.Path

/** Where the currently installed index came from. */
enum class SageApiIndexOrigin {
    EXTERNAL,
    BUNDLED,
    MANUAL,
    UNAVAILABLE,
}

/** Snapshot of the service-owned index loading boundary for diagnostics and probes. */
data class SageApiIndexLoadState(
    val origin: SageApiIndexOrigin,
    val path: Path? = null,
    val sizeBytes: Long? = null,
    val schemaVersion: Int? = null,
    val sageVersion: String? = null,
    val pythonVersion: String? = null,
    val generatorVersion: String? = null,
    val sourceDigestCount: Int = 0,
    val sourceKinds: Set<String> = emptySet(),
    val entryCount: Int = 0,
    val error: String? = null,
)

/**
 * Application-scoped holder for the validated Sage API index.
 *
 * A configured external path is authoritative: when it is present but cannot be
 * loaded, this service stays unavailable instead of silently falling back to the
 * small bundled fixture. That keeps a product configured for a full external
 * index from appearing healthy while serving incomplete bundled data. The full
 * generated index therefore remains an external validation/product input and is
 * never copied into plugin resources.
 */
@Service(Service.Level.APP)
class SageApiIndexService {
    @Volatile
    private var current: SageApiIndexQuery? = null

    @Volatile
    private var state: SageApiIndexLoadState = SageApiIndexLoadState(SageApiIndexOrigin.UNAVAILABLE)

    private val loader = SageApiIndexLoader()

    init {
        loadConfiguredOrBundled()
    }

    fun install(query: SageApiIndexQuery?) {
        current = query
        state = if (query == null) {
            SageApiIndexLoadState(SageApiIndexOrigin.UNAVAILABLE)
        } else {
            query.toLoadState(SageApiIndexOrigin.MANUAL, path = null)
        }
    }

    fun query(): SageApiIndexQuery? = current

    /** Returns the last load result without exposing mutable service state. */
    fun loadState(): SageApiIndexLoadState = state

    /**
     * Re-evaluates product configuration. A configured path is tried first;
     * bundled data is used only when neither the property nor environment
     * variable is configured.
     */
    fun reloadConfigured(): Boolean = loadConfiguredOrBundled()

    private fun loadConfiguredOrBundled(): Boolean {
        val raw = System.getProperty(INDEX_PATH_PROPERTY)?.trim()?.takeIf { it.isNotEmpty() }
            ?: System.getenv(INDEX_PATH_ENV)?.trim()?.takeIf { it.isNotEmpty() }
        if (raw == null) return reloadBundled()

        // An explicit external index is a product input, not an optional hint.
        // Do not replace it with the reviewed-but-scoped bundled fixture on error.
        current = null
        val path = runCatching { Path.of(raw) }.getOrNull()
        if (path == null) {
            state = SageApiIndexLoadState(
                origin = SageApiIndexOrigin.UNAVAILABLE,
                error = "Invalid configured Sage API index path: " + raw,
            )
            LOG.warn("Invalid configured Sage API index path: " + raw)
            return false
        }
        return reload(path, SageApiIndexOrigin.EXTERNAL)
    }

    private fun reloadBundled(): Boolean {
        val index = loader.fromResource(javaClass.classLoader, BUNDLED_INDEX_RESOURCE)
        if (index == null) {
            current = null
            state = SageApiIndexLoadState(
                origin = SageApiIndexOrigin.UNAVAILABLE,
                error = "Bundled Sage API index is missing or invalid",
            )
            LOG.warn("Cannot load bundled Sage API index; indexed completion remains unavailable")
            return false
        }
        val query = SageApiIndexQuery(index)
        current = query
        state = query.toLoadState(SageApiIndexOrigin.BUNDLED, path = null, sizeBytes = null)
        return true
    }

    fun reload(path: Path): Boolean = reload(path, SageApiIndexOrigin.EXTERNAL)

    private fun reload(path: Path, origin: SageApiIndexOrigin): Boolean {
        // External configuration is fail-closed. Never leave a stale query
        // available when the selected artifact cannot be inspected or loaded.
        current = null
        val sizeBytes = runCatching {
            require(Files.isRegularFile(path)) { "Configured Sage API index is not a regular file" }
            Files.size(path)
        }.getOrElse { error ->
            state = SageApiIndexLoadState(
                origin = SageApiIndexOrigin.UNAVAILABLE,
                path = path,
                error = error.message ?: "Cannot inspect Sage API index from " + path,
            )
            LOG.warn("Cannot inspect Sage API index from " + path, error)
            return false
        }
        if (sizeBytes > MAX_EXTERNAL_INDEX_BYTES) {
            state = SageApiIndexLoadState(
                origin = SageApiIndexOrigin.UNAVAILABLE,
                path = path,
                sizeBytes = sizeBytes,
                error = "Sage API index exceeds maximum supported size of " + MAX_EXTERNAL_INDEX_BYTES + " bytes",
            )
            LOG.warn("Refusing oversized Sage API index at " + path + " (" + sizeBytes + " bytes)")
            return false
        }

        val index = loader.fromPath(path)
        if (index == null) {
            state = SageApiIndexLoadState(
                origin = SageApiIndexOrigin.UNAVAILABLE,
                path = path,
                sizeBytes = sizeBytes,
                error = "Cannot load Sage API index from " + path,
            )
            LOG.warn("Cannot load Sage API index from " + path)
            return false
        }
        if (index.entries.size > MAX_INDEX_ENTRIES) {
            state = SageApiIndexQuery(index).toLoadState(
                origin = SageApiIndexOrigin.UNAVAILABLE,
                path = path,
                sizeBytes = sizeBytes,
                error = "Sage API index exceeds maximum supported entry count of " + MAX_INDEX_ENTRIES,
            )
            LOG.warn("Refusing Sage API index at " + path + " with " + index.entries.size + " entries")
            return false
        }
        val query = SageApiIndexQuery(index)
        current = query
        state = query.toLoadState(origin, path, sizeBytes)
        return true
    }

    companion object {
        const val INDEX_PATH_PROPERTY = "sage.api.index"
        const val INDEX_PATH_ENV = "SAGE_API_INDEX"
        private const val BUNDLED_INDEX_RESOURCE = "sage-api-index.json"
        /** Hard cap protects IDE startup from accidental multi-hundred-MB inputs. */
        const val MAX_EXTERNAL_INDEX_BYTES: Long = 256L * 1024L * 1024L
        /** Entry cap leaves headroom for future index growth without OOM risk. */
        const val MAX_INDEX_ENTRIES: Int = 200_000
        private val LOG = Logger.getInstance(SageApiIndexService::class.java)

        fun getInstance(): SageApiIndexService =
            ApplicationManager.getApplication().getService(SageApiIndexService::class.java)
    }
}

private fun SageApiIndexQuery.toLoadState(
    origin: SageApiIndexOrigin,
    path: Path?,
    sizeBytes: Long? = null,
    error: String? = null,
): SageApiIndexLoadState = SageApiIndexLoadState(
    origin = origin,
    path = path,
    sizeBytes = sizeBytes,
    schemaVersion = index.schemaVersion,
    sageVersion = index.sageVersion,
    pythonVersion = index.pythonVersion,
    generatorVersion = index.generatorVersion,
    sourceDigestCount = index.sourceDigests.size,
    sourceKinds = index.entries.asSequence().flatMap { it.sources.asSequence() }.map { it.kind.name }.toSet(),
    entryCount = index.entries.size,
    error = error,
)
