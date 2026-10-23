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
    LOADING,
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
    val psiOnly: Boolean = false,
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
class SageApiIndexService(
    private val enqueueInitialLoad: (Runnable) -> Unit,
) {
    /** Required by the IntelliJ application-service container. */
    constructor() : this({ task -> ApplicationManager.getApplication().executeOnPooledThread(task) })

    private val publicationLock = Any()

    @Volatile
    private var loadGeneration: Long = 0

    @Volatile
    private var current: SageApiIndexQuery? = null

    @Volatile
    private var state: SageApiIndexLoadState = SageApiIndexLoadState(SageApiIndexOrigin.UNAVAILABLE)

    private val loader = SageApiIndexLoader()

    init {
        val generation = beginLoading()
        runCatching {
            enqueueInitialLoad(Runnable { loadConfiguredOrBundled(generation) })
        }.onFailure {
            unavailable(generation, null, "Cannot schedule initial Sage API index load")
        }
    }

    fun install(query: SageApiIndexQuery?) {
        synchronized(publicationLock) {
            loadGeneration++
            current = query
            state = if (query == null) {
                SageApiIndexLoadState(SageApiIndexOrigin.UNAVAILABLE)
            } else {
                query.toLoadState(SageApiIndexOrigin.MANUAL, path = null)
            }
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
    fun reloadConfigured(): Boolean {
        val generation = beginLoading()
        return loadConfiguredOrBundled(generation)
    }

    private fun beginLoading(path: Path? = null): Long = synchronized(publicationLock) {
        loadGeneration++
        current = null
        state = SageApiIndexLoadState(SageApiIndexOrigin.LOADING, path = path)
        loadGeneration
    }

    private fun isCurrent(generation: Long): Boolean = loadGeneration == generation

    private fun publish(
        generation: Long,
        query: SageApiIndexQuery?,
        newState: SageApiIndexLoadState,
    ): Boolean = synchronized(publicationLock) {
        if (loadGeneration != generation) return@synchronized false
        current = query
        state = newState
        true
    }

    private fun loadConfiguredOrBundled(generation: Long): Boolean {
        if (!isCurrent(generation)) return false
        val raw = System.getProperty(INDEX_PATH_PROPERTY)?.trim()?.takeIf { it.isNotEmpty() }
            ?: System.getenv(INDEX_PATH_ENV)?.trim()?.takeIf { it.isNotEmpty() }
        if (raw != null) {
            // An explicit external index is a product input, not an optional hint.
            // Do not replace it with the reviewed-but-scoped bundled fixture on error.
            val path = runCatching { Path.of(raw) }.getOrNull()
            if (path == null) {
                return unavailable(generation, null, "Invalid configured Sage API index path: " + raw)
            }
            return reload(path, generation, SageApiIndexOrigin.EXTERNAL)
        }

        val configuredProduct = System.getProperty(PRODUCT_INDEX_PATH_PROPERTY)?.trim()?.takeIf { it.isNotEmpty() }
        if (configuredProduct != null) {
            val path = runCatching { Path.of(configuredProduct) }.getOrNull()
                ?: return unavailable(generation, null, "Invalid configured Sage API product sidecar path")
            return reloadProductSidecar(path, generation)
        }

        val productPath = productIndexPath()
        if (productPath != null) return reloadProductSidecar(productPath, generation)
        return reloadBundled(generation)
    }

    private fun productIndexPath(): Path? = findProductIndexPath(
        runCatching { PathManager.getHomeDir() }.getOrNull(),
        runCatching { PathManager.getConfigDir() }.getOrNull(),
    )

    /**
     * The bundled product stages the sidecar into the IDE home, while
     * sage-pycharm-stubgen installs it into the user-level config directory
     * (APPDATA JetBrains PyCharm config dir, sage-api/<version>/) —
     * reachable in a stock IDE only through this lookup.  Without the
     * config fallback the sidecar sits unread and the plugin quietly runs
     * on the small bundled fixture, leaving completion to PyCharm's native
     * WSL stub index, whose IJent backend is exactly the unreliable layer
     * this pipeline exists to bypass.
     */
    private fun findProductIndexPath(homeDir: Path?, configDir: Path?): Path? {
        val relative = java.nio.file.Paths.get(PRODUCT_INDEX_RELATIVE_PATH)
        for (root in listOfNotNull(homeDir, configDir)) {
            val path = runCatching { root.resolve(relative) }.getOrNull() ?: continue
            val directory = path.parent ?: continue
            val declared = listOf(path, directory.resolve(PRODUCT_ENVELOPE_FILE), directory.resolve(PRODUCT_RECEIPT_FILE))
                .any { Files.exists(it) }
            if (declared) return path
        }
        return null
    }

    private fun reloadProductSidecar(path: Path, generation: Long): Boolean {
        val directory = path.parent
        if (directory == null) return unavailable(generation, path, "Product Sage API index has no parent directory")
        val metadata = readProductMetadata(directory)
            ?: return unavailable(generation, path, "Product Sage API index sidecar metadata is missing or invalid")
        if (metadata.receiptOnly) {
            // PSI mode: the JSON index is replaced by an index built from the
            // local stub-tree mirror via SagePsiApiIndexFactory, so every rich
            // consumer keeps its SageApiIndexQuery with zero changes.  The
            // loadState first flips to psiOnly (available immediately), then
            // the background build publishes the query.
            val psiState = SageApiIndexLoadState(
                SageApiIndexOrigin.PRODUCT,
                path = path,
                schemaVersion = 1,
                entryCount = metadata.entryCount ?: 0,
                artifactId = metadata.artifactId,
                psiOnly = true,
            )
            if (!publish(generation, null, psiState)) return false
            LOG.info("Sage API receipt-only sidecar active (PSI mode): " + path)
            val sidecarDirectory = path.parent
            enqueueInitialLoad(Runnable { buildPsiIndex(generation, sidecarDirectory, metadata) })
            return true
        }
        return reload(
            path,
            generation,
            SageApiIndexOrigin.PRODUCT,
            metadata.sha256,
            metadata.artifactId,
            metadata.entryCount,
        )
    }

    private fun readProductMetadata(directory: Path): ProductSidecarMetadata? {
        val envelopePath = directory.resolve(PRODUCT_ENVELOPE_FILE)
        val receiptPath = directory.resolve(PRODUCT_RECEIPT_FILE)
        if (!Files.isRegularFile(envelopePath) || !Files.isRegularFile(receiptPath)) return null
        val envelope = runCatching { Files.readString(envelopePath) }.getOrNull() ?: return null
        val indexObject = jsonObject(envelope, "index")
        if (indexObject == null) {
            // Receipt-only sidecar (goal C): the stubTree section replaces the
            // index; the platform StubIndex over the local mirror serves the
            // queries this service used to answer from the JSON index.
            return receiptOnlyMetadata(directory, envelope, artifactIdOf(envelope))
        }
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

    private fun artifactIdOf(envelope: String): String? =
        jsonString(envelope, "artifactId")?.takeIf { it.isNotBlank() }

    /** Validates the goal-C receipt shape: coverage + stub tree, no index. */
    private fun receiptOnlyMetadata(directory: Path, envelope: String, artifactId: String?): ProductSidecarMetadata? {
        val receipt = runCatching { Files.readString(directory.resolve(PRODUCT_RECEIPT_FILE)) }.getOrNull() ?: return null
        if (jsonNumber(envelope, "schemaVersion") != 1) return null
        val coverage = jsonObject(envelope, "apiCoverage") ?: return null
        if (jsonString(coverage, "scope") != "FULL" || !jsonBoolean(coverage, "isComplete")) return null
        val covered = jsonNumber(coverage, "coveredCount") ?: return null
        if (covered != jsonNumber(coverage, "expectedCount")) return null
        if (artifactId == null) return null
        if (jsonString(receipt, "artifactId") != artifactId) return null
        val stubTree = jsonObject(envelope, "stubTree") ?: return null
        val fileCount = jsonNumber(stubTree, "fileCount") ?: return null
        if (fileCount != covered || fileCount <= 0) return null
        val digest = jsonString(stubTree, "sha256")?.lowercase()?.takeIf { SHA256.matches(it) } ?: return null
        return ProductSidecarMetadata(sha256 = digest, artifactId = artifactId, entryCount = fileCount, receiptOnly = true)
    }

    private fun jsonObject(json: String, key: String): String? =
        Regex("""(?s)"$key"\s*:\s*\{(.*?)\}""").find(json)?.groupValues?.get(1)

    private fun jsonString(json: String, key: String): String? =
        Regex(""""$key"\s*:\s*"([^"]*)"""").find(json)?.groupValues?.get(1)

    private fun jsonNumber(json: String, key: String): Int? =
        Regex(""""$key"\s*:\s*(\d+)""").find(json)?.groupValues?.get(1)?.toIntOrNull()

    private fun jsonBoolean(json: String, key: String): Boolean =
        Regex(""""$key"\s*:\s*true""").containsMatchIn(json)

    private fun unavailable(generation: Long, path: Path?, message: String, sizeBytes: Long? = null): Boolean {
        if (publish(
                generation,
                null,
                SageApiIndexLoadState(SageApiIndexOrigin.UNAVAILABLE, path = path, sizeBytes = sizeBytes, error = message),
            )
        ) {
            LOG.warn(message + (path?.let { ": $it" } ?: ""))
        }
        return false
    }

    private fun reloadBundled(generation: Long): Boolean {
        if (!isCurrent(generation)) return false
        val index = loader.fromResource(javaClass.classLoader, BUNDLED_INDEX_RESOURCE)
        if (index == null) {
            return unavailable(generation, null, "Bundled Sage API index is missing or invalid")
        }
        val query = SageApiIndexQuery(index)
        return publish(generation, query, query.toLoadState(SageApiIndexOrigin.BUNDLED, path = null, sizeBytes = null))
    }

    fun reload(path: Path): Boolean {
        val generation = beginLoading(path)
        return reload(path, generation, SageApiIndexOrigin.EXTERNAL)
    }

    private fun reload(
        path: Path,
        generation: Long,
        origin: SageApiIndexOrigin,
        expectedSha256: String? = null,
        artifactId: String? = null,
        expectedEntryCount: Int? = null,
    ): Boolean {
        if (!isCurrent(generation)) return false
        // External configuration is fail-closed. Never leave a stale query
        // available when the selected artifact cannot be inspected or loaded.
        val sizeBytes = runCatching {
            require(Files.isRegularFile(path)) { "Configured Sage API index is not a regular file" }
            Files.size(path)
        }.getOrElse { error ->
            return unavailable(generation, path, error.message ?: ("Cannot inspect Sage API index from " + path))
        }
        if (sizeBytes > MAX_EXTERNAL_INDEX_BYTES) {
            return unavailable(
                generation,
                path,
                "Sage API index exceeds maximum supported size of " + MAX_EXTERNAL_INDEX_BYTES + " bytes",
                sizeBytes,
            )
        }
        val actualSha256 = if (expectedSha256 == null) {
            null
        } else {
            runCatching { sha256(path) }.getOrElse {
                return unavailable(generation, path, "Cannot calculate Sage API index SHA-256")
            }
        }
        if (expectedSha256 != null && actualSha256 != expectedSha256.lowercase()) {
            return unavailable(generation, path, "Sage API index SHA-256 does not match the product receipt")
        }

        if (!isCurrent(generation)) return false
        val index = loader.fromPath(path)
        if (index == null) {
            return unavailable(generation, path, "Cannot load Sage API index from " + path)
        }
        if (expectedEntryCount != null && index.entries.size != expectedEntryCount) {
            return unavailable(generation, path, "Sage API index entry count does not match the product receipt")
        }
        if (index.entries.size > MAX_INDEX_ENTRIES) {
            val unavailableState = SageApiIndexQuery(index).toLoadState(
                origin = SageApiIndexOrigin.UNAVAILABLE,
                path = path,
                sizeBytes = sizeBytes,
                error = "Sage API index exceeds maximum supported entry count of " + MAX_INDEX_ENTRIES,
            )
            if (publish(generation, null, unavailableState)) {
                LOG.warn("Refusing Sage API index at " + path + " with " + index.entries.size + " entries")
            }
            return false
        }
        val query = SageApiIndexQuery(index)
        LOG.info(
            "Sage API index loaded: origin=$origin entries=${index.entries.size} " +
                "bytes=$sizeBytes path=$path generator=${index.generatorVersion}",
        )
        return publish(
            generation,
            query,
            query.toLoadState(
                origin,
                path,
                sizeBytes,
                verifiedSha256 = actualSha256,
                artifactId = artifactId,
            ),
        )
    }

    /** Builds the PSI-backed index from the stub-tree mirror and publishes it. */
    private fun buildPsiIndex(generation: Long, sidecarDirectory: Path?, metadata: ProductSidecarMetadata) {
        if (!isCurrent(generation)) return
        val directory = sidecarDirectory ?: return
        val mirror = directory.resolve(STUB_TREE_DIRECTORY)
        if (!Files.isDirectory(mirror)) {
            LOG.warn("Sage PSI index: no stub-tree mirror beside the sidecar: " + mirror)
            return
        }
        val project = com.intellij.openapi.application.ApplicationManager.getApplication().runReadAction<com.intellij.openapi.project.Project?> {
            // Any open project works: the mirror is application-level data and
            // the PSI parse is project-agnostic for library files.
            com.intellij.openapi.project.ProjectManager.getInstance().openProjects.firstOrNull()
        } ?: return
        // Resolve + refresh the mirror OUTSIDE the read action: a synchronous
        // VFS refresh under a read lock is a platform error, and the factory
        // itself refreshes recursively once inside.  refreshAndFindFileByNioFile
        // without events is read-action safe for the initial resolve.
        // Recursive tree refresh outside any lock; children become visible
        // to the walk below.
        com.intellij.openapi.vfs.VfsUtil.markDirtyAndRefresh(false, true, true, mirror)
        val fileSystem = com.intellij.openapi.vfs.LocalFileSystem.getInstance()
        val mirrorRoot = com.intellij.openapi.application.ReadAction.compute<com.intellij.openapi.vfs.VirtualFile?, Exception> {
            fileSystem.refreshAndFindFileByNioFile(mirror)
        } ?: run {
            LOG.warn("Sage PSI index: mirror not found in VFS: " + mirror)
            return
        }
        val index = com.intellij.openapi.application.ReadAction.compute<com.starnotesxj.sagemath.sageapi.SageApiIndex?, Exception> {
            SagePsiApiIndexFactory.build(project, mirrorRoot, metadataSageVersion(directory), "3.13")
        }
        if (index == null || !isCurrent(generation)) return
        val query = SageApiIndexQuery(index)
        publish(
            generation,
            query,
            query.toLoadState(SageApiIndexOrigin.PRODUCT, path = directory.resolve(PRODUCT_INDEX_FILE), psiOnly = true),
        )
        LOG.info("Sage PSI index active: ${index.entries.size} entries")
    }

    private fun metadataSageVersion(sidecarDirectory: Path): String =
        sidecarDirectory.fileName?.toString()?.takeIf { it.isNotEmpty() } ?: "10.9"

    companion object {
        const val INDEX_PATH_PROPERTY = "sage.api.index"
        const val INDEX_PATH_ENV = "SAGE_API_INDEX"
        const val PRODUCT_INDEX_PATH_PROPERTY = "sage.api.product.index"
        const val PRODUCT_INDEX_RELATIVE_PATH = "sage-api/10.9/sage-api-index.json"
        private const val PRODUCT_INDEX_FILE = "sage-api-index.json"
        private const val PRODUCT_ENVELOPE_FILE = "sage-api-index-envelope.json"
        private const val PRODUCT_RECEIPT_FILE = "artifact-receipt.json"
        private const val BUNDLED_INDEX_RESOURCE = "sage-api-index.json"
        private const val STUB_TREE_DIRECTORY = "stub-tree"
        private val SHA256 = Regex("[0-9a-f]{64}")
        /** Hard cap protects IDE startup from accidental multi-hundred-MB inputs. */
        const val MAX_EXTERNAL_INDEX_BYTES: Long = 288L * 1024L * 1024L
        /**
         * Entry cap leaves headroom for future index growth without OOM risk.
         * Measured on the sage-pycharm-stubgen 0.9.10 corpus (Sage 10.9,
         * --include-py): 174,827 entries / ~165 MB compact JSON (~0.95 KB per
         * entry, 77% of payload is METHOD entries).  The 250k entry cap pairs
         * with the 288 MB byte cap at that density.
         */
        const val MAX_INDEX_ENTRIES: Int = 250_000
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
    psiOnly: Boolean = false,
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
    psiOnly = psiOnly,
)
