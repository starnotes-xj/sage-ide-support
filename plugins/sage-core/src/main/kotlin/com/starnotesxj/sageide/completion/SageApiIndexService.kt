package com.starnotesxj.sageide.completion

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.PathManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.diagnostic.Logger
import com.starnotesxj.sagemath.sageapi.SageApiIndexLoader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import java.nio.file.Files
import java.nio.file.Path

/** Where the currently installed index came from. */
enum class SageApiIndexOrigin {
    EXTERNAL,
    PRODUCT,
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
    val verifiedSha256: String? = null,
    val artifactId: String? = null,
    val error: String? = null,
)

/**
 * Application-scoped holder for the validated Sage API index.
 *
 * A configured external path is authoritative: when it is present but cannot be
 * loaded, this service stays unavailable instead of silently falling back to the
 * small bundled fixture. That keeps a product configured for a full external
 * index from appearing healthy while serving incomplete bundled data. The full
 * generated index is installed as an explicitly staged product sidecar rather than
 * copied into plugin resources. The sidecar has a SHA-256 receipt and is selected
 * only from the installed IDE home; malformed or mismatched sidecars fail closed.
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
        if (raw != null) {
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

        val configuredProduct = System.getProperty(PRODUCT_INDEX_PATH_PROPERTY)?.trim()?.takeIf { it.isNotEmpty() }
        if (configuredProduct != null) {
            val path = runCatching { Path.of(configuredProduct) }.getOrNull()
                ?: return unavailable(null, "Invalid configured Sage API product sidecar path")
            return reloadProductSidecar(path)
        }

        val productPath = productIndexPath()
        if (productPath != null) return reloadProductSidecar(productPath)
        return reloadBundled()
    }

    private fun productIndexPath(): Path? {
        val path = runCatching {
            PathManager.getHomeDir().resolve(PRODUCT_INDEX_RELATIVE_PATH)
        }.getOrNull() ?: return null
        val directory = path.parent ?: return null
        val declared = listOf(path, directory.resolve(PRODUCT_ENVELOPE_FILE), directory.resolve(PRODUCT_RECEIPT_FILE))
            .any { Files.exists(it) }
        return path.takeIf { declared }
    }

    private fun reloadProductSidecar(path: Path): Boolean {
        val directory = path.parent
        if (directory == null) return unavailable(path, "Product Sage API index has no parent directory")
        val metadata = readProductMetadata(directory)
            ?: return unavailable(path, "Product Sage API index sidecar metadata is missing or invalid")
        return reload(path, SageApiIndexOrigin.PRODUCT, metadata.sha256, metadata.artifactId, metadata.entryCount)
    }

    private fun readProductMetadata(directory: Path): ProductSidecarMetadata? {
        val envelopePath = directory.resolve(PRODUCT_ENVELOPE_FILE)
        val receiptPath = directory.resolve(PRODUCT_RECEIPT_FILE)
        if (!Files.isRegularFile(envelopePath) || !Files.isRegularFile(receiptPath)) return null
        val envelope = runCatching { Files.readString(envelopePath) }.getOrNull() ?: return null
        val indexObject = jsonObject(envelope, "index") ?: return null
        val digest = jsonString(indexObject, "sha256")?.lowercase()?.takeIf { SHA256.matches(it) } ?: return null
        if (jsonString(indexObject, "path") != PRODUCT_INDEX_FILE) return null
        if (jsonNumber(envelope, "schemaVersion") != 1) return null
        val coverage = jsonObject(envelope, "apiCoverage") ?: return null
        if (jsonString(coverage, "scope") != "FULL" || !jsonBoolean(coverage, "isComplete")) return null
        if (jsonNumber(coverage, "coveredCount") == null || jsonNumber(coverage, "expectedCount") == null) return null
        if (jsonNumber(coverage, "coveredCount") != jsonNumber(coverage, "expectedCount")) return null
        val artifactId = jsonString(envelope, "artifactId")?.takeIf { it.isNotBlank() } ?: return null
        val receipt = runCatching { Files.readString(receiptPath) }.getOrNull() ?: return null
        val receiptArtifactId = jsonString(receipt, "artifactId") ?: return null
        if (receiptArtifactId != artifactId) return null
        val envelopeEntryCount = jsonNumber(indexObject, "entryCount") ?: return null
        val receiptIndex = jsonObject(receipt, "index") ?: return null
        if (jsonString(receiptIndex, "path") != PRODUCT_INDEX_FILE) return null
        if (jsonString(receiptIndex, "sha256")?.lowercase() != digest) return null
        val receiptEntryCount = jsonNumber(receiptIndex, "entryCount") ?: return null
        if (receiptEntryCount != envelopeEntryCount) return null
        return ProductSidecarMetadata(digest, artifactId, envelopeEntryCount)
    }

    private fun jsonObject(json: String, key: String): String? =
        Regex("""(?s)"$key"\s*:\s*\{(.*?)\}""").find(json)?.groupValues?.get(1)

    private fun jsonString(json: String, key: String): String? =
        Regex(""""$key"\s*:\s*"([^"]*)"""").find(json)?.groupValues?.get(1)

    private fun jsonNumber(json: String, key: String): Int? =
        Regex(""""$key"\s*:\s*(\d+)""").find(json)?.groupValues?.get(1)?.toIntOrNull()

    private fun jsonBoolean(json: String, key: String): Boolean =
        Regex(""""$key"\s*:\s*true""").containsMatchIn(json)

    private fun unavailable(path: Path?, message: String): Boolean {
        current = null
        state = SageApiIndexLoadState(SageApiIndexOrigin.UNAVAILABLE, path = path, error = message)
        LOG.warn(message + (path?.let { ": $it" } ?: ""))
        return false
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

    private fun reload(
        path: Path,
        origin: SageApiIndexOrigin,
        expectedSha256: String? = null,
        artifactId: String? = null,
        expectedEntryCount: Int? = null,
    ): Boolean {
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
        val actualSha256 = if (expectedSha256 == null) {
            null
        } else {
            runCatching { sha256(path) }.getOrElse {
                return unavailable(path, "Cannot calculate Sage API index SHA-256")
            }
        }
        if (expectedSha256 != null && actualSha256 != expectedSha256.lowercase()) {
            return unavailable(path, "Sage API index SHA-256 does not match the product receipt")
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
        if (expectedEntryCount != null && index.entries.size != expectedEntryCount) {
            return unavailable(path, "Sage API index entry count does not match the product receipt")
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
        state = query.toLoadState(
            origin,
            path,
            sizeBytes,
            verifiedSha256 = actualSha256,
            artifactId = artifactId,
        )
        return true
    }

    companion object {
        const val INDEX_PATH_PROPERTY = "sage.api.index"
        const val INDEX_PATH_ENV = "SAGE_API_INDEX"
        const val PRODUCT_INDEX_PATH_PROPERTY = "sage.api.product.index"
        const val PRODUCT_INDEX_RELATIVE_PATH = "sage-api/10.9/sage-api-index.json"
        private const val PRODUCT_INDEX_FILE = "sage-api-index.json"
        private const val PRODUCT_ENVELOPE_FILE = "sage-api-index-envelope.json"
        private const val PRODUCT_RECEIPT_FILE = "artifact-receipt.json"
        private const val BUNDLED_INDEX_RESOURCE = "sage-api-index.json"
        private val SHA256 = Regex("[0-9a-f]{64}")
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
    verifiedSha256: String? = null,
    artifactId: String? = null,
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
    verifiedSha256 = verifiedSha256,
    artifactId = artifactId,
    error = error,
)
