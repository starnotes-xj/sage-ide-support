package com.starnotesxj.sagemath.runtime

import java.io.IOException
import java.net.ProxySelector
import java.net.URI
import java.net.http.HttpClient
import java.net.http.HttpRequest
import java.net.http.HttpResponse
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.security.KeyFactory
import java.security.PublicKey
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.time.Duration
import java.time.Instant
import java.util.Base64
import java.util.UUID

private fun decodeStrictUtf8(bytes: ByteArray): String = runCatching {
    StandardCharsets.UTF_8.newDecoder()
        .onMalformedInput(CodingErrorAction.REPORT)
        .onUnmappableCharacter(CodingErrorAction.REPORT)
        .decode(java.nio.ByteBuffer.wrap(bytes))
        .toString()
}.getOrElse { throw IllegalArgumentException("Runtime catalog is not valid UTF-8", it) }

/** Stable machine-readable failure categories exposed to Settings and SDK adapters. */
enum class RuntimeDiagnosticCode {
    CATALOG_SCHEMA_UNSUPPORTED,
    CATALOG_PARSE_INVALID,
    CATALOG_SIGNATURE_INVALID,
    CATALOG_KEY_UNTRUSTED,
    CATALOG_NETWORK_ERROR,
    CATALOG_TIMEOUT,
    CATALOG_CANCELLED,
    CATALOG_DISK_ERROR,
    CATALOG_CACHE_INVALID,
    CATALOG_TOO_LARGE,
    CURRENT_POINTER_MISSING,
    CURRENT_POINTER_CORRUPT,
    CURRENT_RUNTIME_INVALID,
    RUNTIME_NOT_INSTALLED,
    RUNTIME_ALREADY_CURRENT,
    RUNTIME_SELECT_FAILED,
    RUNTIME_REMOVE_FAILED,
    RUNTIME_ROLLBACK_UNAVAILABLE,
    RUNTIME_IO_ERROR,
    PATH_MAPPING_REQUIRED,
    PATH_OUTSIDE_MAPPING,
    TARGET_INVALID,
    TARGET_PROBE_FAILED,
}

data class RuntimeDiagnostic(
    val code: RuntimeDiagnosticCode,
    val stage: String,
    val message: String,
    val details: Map<String, String> = emptyMap(),
    val causeType: String? = null,
)

data class RuntimeOperationResult<T>(
    val value: T?,
    val diagnostics: List<RuntimeDiagnostic> = emptyList(),
    val succeeded: Boolean = value != null,
)

data class RuntimeCatalogDocument(
    val catalogId: String,
    val generatedAt: Instant = Instant.now(),
    val artifacts: List<RuntimeArtifact>,
    val schemaVersion: Int = 1,
) {
    init {
        require(schemaVersion == 1) { "Unsupported runtime catalog schema: $schemaVersion" }
        require(catalogId.isNotBlank() && catalogId.none(Char::isISOControl)) {
            "Runtime catalog id must be non-blank and printable"
        }
        require(artifacts.map { it.id }.toSet().size == artifacts.size) {
            "Runtime catalog contains duplicate runtime ids"
        }
    }
}

/** Canonical, dependency-free catalog encoding used as the Ed25519 signature input. */
object RuntimeCatalogCodec {
    const val MAX_ENCODED_BYTES = 4 * 1024 * 1024
    private const val MAX_LINE_LENGTH = 32 * 1024
    private const val MAX_ARTIFACTS = 10_000
    private const val SCHEMA_VERSION = "schemaVersion"
    private const val CATALOG_ID = "catalogId"
    private const val GENERATED_AT = "generatedAt"
    private const val ARTIFACT = "artifact"

    fun encode(document: RuntimeCatalogDocument): ByteArray = buildString {
        appendLine("$SCHEMA_VERSION=${document.schemaVersion}")
        appendLine("$CATALOG_ID=${encodeValue(document.catalogId)}")
        appendLine("$GENERATED_AT=${document.generatedAt}")
        document.artifacts
            .sortedWith(compareBy<RuntimeArtifact>({ it.id.stableName() }, { it.uri.toString() }))
            .forEach { artifact ->
                val values = listOf(
                    artifact.id.version,
                    artifact.id.distribution,
                    artifact.id.platform.os.name,
                    artifact.id.platform.architecture.name,
                    artifact.id.platform.libc?.name.orEmpty(),
                    artifact.uri.toString(),
                    artifact.archiveFormat.name,
                    artifact.sizeBytes?.toString().orEmpty(),
                    artifact.sha256.lowercase(),
                    artifact.entrypoint,
                    artifact.manifestUri?.toString().orEmpty(),
                    artifact.publishedAt?.toString().orEmpty(),
                    artifact.metadata.entries
                        .sortedBy { it.key }
                        .joinToString(",") { "${encodeValue(it.key)}~${encodeValue(it.value)}" },
                )
                appendLine("$ARTIFACT=${values.joinToString("|") { encodeValue(it) }}")
            }
    }.toByteArray(StandardCharsets.UTF_8).also {
        require(it.size in 1..MAX_ENCODED_BYTES) { "Runtime catalog is too large" }
    }

    fun decode(bytes: ByteArray): RuntimeCatalogDocument = decode(decodeStrictUtf8(bytes))

    fun decode(text: String): RuntimeCatalogDocument {
        require(text.toByteArray(StandardCharsets.UTF_8).size in 1..MAX_ENCODED_BYTES) {
            "Runtime catalog is too large"
        }
        val values = linkedMapOf<String, String>()
        val artifacts = mutableListOf<RuntimeArtifact>()
        text.lineSequence().filter(String::isNotEmpty).forEach { line ->
            require(line.length <= MAX_LINE_LENGTH) { "Runtime catalog line is too long" }
            val separator = line.indexOf('=')
            require(separator > 0) { "Malformed runtime catalog line" }
            val key = line.substring(0, separator)
            val value = line.substring(separator + 1)
            if (key == ARTIFACT) {
                require(artifacts.size < MAX_ARTIFACTS) { "Runtime catalog contains too many artifacts" }
                artifacts += decodeArtifact(value)
            }
            else {
                require(key in setOf(SCHEMA_VERSION, CATALOG_ID, GENERATED_AT)) {
                    "Unknown runtime catalog field: $key"
                }
                require(values.put(key, value) == null) { "Duplicate runtime catalog field: $key" }
            }
        }
        val required: (String) -> String = { key -> values[key] ?: error("Missing runtime catalog field: $key") }
        return RuntimeCatalogDocument(
            schemaVersion = required(SCHEMA_VERSION).toIntOrNull()
                ?: error("Invalid runtime catalog schema"),
            catalogId = decodeValue(required(CATALOG_ID)),
            generatedAt = runCatching { Instant.parse(required(GENERATED_AT)) }
                .getOrElse { error("Invalid runtime catalog timestamp") },
            artifacts = artifacts,
        )
    }

    private fun decodeArtifact(value: String): RuntimeArtifact {
        val parts = value.split('|')
        require(parts.size == 13) { "Malformed runtime catalog artifact" }
        val decoded = parts.map(::decodeValue)
        val os = enumValue<OperatingSystem>(decoded[2], "runtimeOs")
        val architecture = enumValue<CpuArchitecture>(decoded[3], "runtimeArchitecture")
        val libc = decoded[4].takeIf(String::isNotEmpty)?.let { enumValue<Libc>(it, "runtimeLibc") }
        val metadata = if (decoded[12].isEmpty()) {
            emptyMap()
        }
        else {
            decoded[12].split(',').associate { entry ->
                val pair = entry.split('~')
                require(pair.size == 2) { "Malformed runtime catalog metadata" }
                val key = decodeValue(pair[0])
                require(key.isNotEmpty()) { "Runtime catalog metadata key must not be empty" }
                key to decodeValue(pair[1])
            }
        }
        return RuntimeArtifact(
            id = SageRuntimeId(decoded[0], PlatformTriple(os, architecture, libc), decoded[1]),
            uri = runCatching { URI(decoded[5]) }.getOrElse { error("Invalid runtime artifact URI") },
            archiveFormat = enumValue(decoded[6], "archiveFormat"),
            sizeBytes = decoded[7].takeIf(String::isNotEmpty)?.toLongOrNull()
                ?: decoded[7].takeIf(String::isNotEmpty)?.let { error("Invalid runtime artifact size") },
            sha256 = decoded[8],
            entrypoint = decoded[9],
            manifestUri = decoded[10].takeIf(String::isNotEmpty)?.let {
                runCatching { URI(it) }.getOrElse { error("Invalid runtime manifest URI") }
            },
            publishedAt = decoded[11].takeIf(String::isNotEmpty)?.let {
                runCatching { Instant.parse(it) }.getOrElse { error("Invalid runtime published timestamp") }
            },
            metadata = metadata,
        )
    }

    private fun encodeValue(value: String): String = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(value.toByteArray(StandardCharsets.UTF_8))

    private fun decodeValue(value: String): String = runCatching {
        decodeStrictUtf8(Base64.getUrlDecoder().decode(value))
    }.getOrElse { error("Invalid encoded runtime catalog value") }

    private inline fun <reified T : Enum<T>> enumValue(value: String, field: String): T =
        runCatching { enumValueOf<T>(value) }.getOrElse { error("Invalid runtime catalog $field") }
}

data class RuntimeCatalogEnvelope(
    val document: RuntimeCatalogDocument,
    val keyId: String,
    val signature: ByteArray,
    val schemaVersion: Int = 1,
) {
    init {
        require(schemaVersion == 1) { "Unsupported signed runtime catalog schema: $schemaVersion" }
        require(keyId.isNotBlank()) { "Runtime catalog key id must not be blank" }
        require(keyId.toByteArray(StandardCharsets.UTF_8).size <= 256) { "Runtime catalog key id is too large" }
        require(signature.size in 1..4096) { "Runtime catalog signature is too large" }
    }

    override fun equals(other: Any?): Boolean = other is RuntimeCatalogEnvelope &&
        document == other.document && keyId == other.keyId && signature.contentEquals(other.signature) &&
        schemaVersion == other.schemaVersion

    override fun hashCode(): Int = 31 * (31 * (31 * document.hashCode() + keyId.hashCode()) + signature.contentHashCode()) + schemaVersion
}

object SignedRuntimeCatalogCodec {
    const val MAX_ENCODED_BYTES = 8 * 1024 * 1024
    private const val MAX_LINE_LENGTH = 8 * 1024 * 1024
    private const val MAX_SIGNATURE_BYTES = 4096
    private const val MAX_KEY_ID_BYTES = 256
    private const val SCHEMA_VERSION = "schemaVersion"
    private const val KEY_ID = "keyId"
    private const val DOCUMENT = "document"
    private const val SIGNATURE = "signature"

    fun encode(envelope: RuntimeCatalogEnvelope): ByteArray = buildString {
        appendLine("$SCHEMA_VERSION=${envelope.schemaVersion}")
        appendLine("$KEY_ID=${encodeValue(envelope.keyId)}")
        appendLine("$DOCUMENT=${encodeValue(RuntimeCatalogCodec.encode(envelope.document).toString(StandardCharsets.UTF_8))}")
        appendLine("$SIGNATURE=${Base64.getUrlEncoder().withoutPadding().encodeToString(envelope.signature)}")
    }.toByteArray(StandardCharsets.UTF_8).also {
        require(it.size <= MAX_ENCODED_BYTES) { "Signed runtime catalog is too large" }
    }

    fun decode(bytes: ByteArray): RuntimeCatalogEnvelope {
        require(bytes.size in 1..MAX_ENCODED_BYTES) { "Signed runtime catalog is too large" }
        val values = linkedMapOf<String, String>()
        decodeStrictUtf8(bytes).lineSequence().filter(String::isNotEmpty).forEach { line ->
            require(line.length <= MAX_LINE_LENGTH) { "Signed runtime catalog line is too long" }
            val separator = line.indexOf('=')
            require(separator > 0) { "Malformed signed runtime catalog line" }
            val key = line.substring(0, separator)
            require(key in setOf(SCHEMA_VERSION, KEY_ID, DOCUMENT, SIGNATURE)) {
                "Unknown signed runtime catalog field: $key"
            }
            require(values.put(key, line.substring(separator + 1)) == null) {
                "Duplicate signed runtime catalog field: $key"
            }
        }
        val required: (String) -> String = { key -> values[key] ?: error("Missing signed runtime catalog field: $key") }
        val keyId = decodeValue(required(KEY_ID)).also {
            require(it.toByteArray(StandardCharsets.UTF_8).size <= MAX_KEY_ID_BYTES) {
                "Runtime catalog key id is too large"
            }
        }
        val signature = runCatching { Base64.getUrlDecoder().decode(required(SIGNATURE)) }
            .getOrElse { error("Invalid runtime catalog signature encoding") }
            .also { require(it.size in 1..MAX_SIGNATURE_BYTES) { "Runtime catalog signature is too large" } }
        return RuntimeCatalogEnvelope(
            schemaVersion = required(SCHEMA_VERSION).toIntOrNull()
                ?: error("Invalid signed runtime catalog schema"),
            keyId = keyId,
            document = RuntimeCatalogCodec.decode(decodeValue(required(DOCUMENT)).toByteArray(StandardCharsets.UTF_8)),
            signature = signature,
        )
    }

    private fun encodeValue(value: String): String = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(value.toByteArray(StandardCharsets.UTF_8))

    private fun decodeValue(value: String): String = runCatching {
        decodeStrictUtf8(Base64.getUrlDecoder().decode(value))
    }.getOrElse { error("Invalid encoded signed runtime catalog value") }
}

fun interface RuntimeCatalogTrustStore {
    fun publicKey(keyId: String): PublicKey?
}

object BuiltInRuntimeCatalogKeys : RuntimeCatalogTrustStore {
    /** Public-only key. The corresponding signing key is held by the catalog publisher, never by this client. */
    const val KEY_ID = "sage-runtime-catalog-2026-rotating-1"
    private const val PUBLIC_KEY_SPKI_HEX = "302a300506032b6570032100f44300e254da0b5ce84e7975a7b830da42641670251e6c0e4d87927a1568b500"
    val PUBLIC_KEY: PublicKey by lazy {
        KeyFactory.getInstance("Ed25519").generatePublic(X509EncodedKeySpec(hexToBytes(PUBLIC_KEY_SPKI_HEX)))
    }

    override fun publicKey(keyId: String): PublicKey? = PUBLIC_KEY.takeIf { keyId == KEY_ID }

    private fun hexToBytes(value: String): ByteArray = value.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
}

class VerifiedRuntimeCatalog private constructor(
    val document: RuntimeCatalogDocument,
) {
    fun list(query: RuntimeQuery = RuntimeQuery()): List<RuntimeArtifact> = document.artifacts
        .asSequence()
        .filter { query.version == null || it.id.version == query.version }
        .filter { it.id.platform == query.platform }
        .filter { query.distribution == null || it.id.distribution == query.distribution }
        .sortedByDescending { it.publishedAt }
        .toList()

    fun resolve(id: SageRuntimeId): RuntimeArtifact? = document.artifacts.firstOrNull { it.id == id }

    internal companion object {
        fun trusted(document: RuntimeCatalogDocument): VerifiedRuntimeCatalog = VerifiedRuntimeCatalog(document)
    }
}

data class RuntimeCatalogVerificationResult(
    val valid: Boolean,
    val document: RuntimeCatalogDocument?,
    val diagnostics: List<RuntimeDiagnostic> = emptyList(),
    val trustedCatalog: VerifiedRuntimeCatalog? = null,
)

class RuntimeCatalogSignatureVerifier(
    private val trustStore: RuntimeCatalogTrustStore = BuiltInRuntimeCatalogKeys,
) {
    fun verify(envelope: RuntimeCatalogEnvelope): RuntimeCatalogVerificationResult {
        if (envelope.schemaVersion != 1 || envelope.document.schemaVersion != 1) {
            return invalid(RuntimeDiagnosticCode.CATALOG_SCHEMA_UNSUPPORTED, "CATALOG_VERIFY", "Unsupported runtime catalog schema")
        }
        val publicKey = trustStore.publicKey(envelope.keyId)
            ?: return invalid(RuntimeDiagnosticCode.CATALOG_KEY_UNTRUSTED, "CATALOG_VERIFY", "Runtime catalog key is not trusted")
        val valid = runCatching {
            Signature.getInstance("Ed25519").run {
                initVerify(publicKey)
                update(RuntimeCatalogCodec.encode(envelope.document))
                verify(envelope.signature)
            }
        }.getOrElse { false }
        return if (valid) {
            RuntimeCatalogVerificationResult(
                valid = true,
                document = envelope.document,
                trustedCatalog = VerifiedRuntimeCatalog.trusted(envelope.document),
            )
        }
        else {
            invalid(RuntimeDiagnosticCode.CATALOG_SIGNATURE_INVALID, "CATALOG_VERIFY", "Runtime catalog signature verification failed")
        }
    }

    private fun invalid(code: RuntimeDiagnosticCode, stage: String, message: String) =
        RuntimeCatalogVerificationResult(
            valid = false,
            document = null,
            diagnostics = listOf(RuntimeDiagnostic(code, stage, message)),
        )
}

class SignedRuntimeCatalog(
    envelope: RuntimeCatalogEnvelope,
    verifier: RuntimeCatalogSignatureVerifier = RuntimeCatalogSignatureVerifier(),
) : RuntimeCatalog {
    private val trusted: VerifiedRuntimeCatalog = verifier.verify(envelope).let {
        require(it.valid) { it.diagnostics.joinToString { diagnostic -> diagnostic.message } }
        it.trustedCatalog!!
    }

    override fun list(query: RuntimeQuery): List<RuntimeArtifact> = trusted.list(query)
}

enum class RuntimeCatalogLoadSource {
    PRIMARY,
    MIRROR,
    CACHE,
    NONE,
}

data class RuntimeCatalogLoadResult(
    val succeeded: Boolean,
    val document: RuntimeCatalogDocument?,
    val source: RuntimeCatalogLoadSource,
    val diagnostics: List<RuntimeDiagnostic> = emptyList(),
    val trustedCatalog: VerifiedRuntimeCatalog? = null,
)

fun interface RuntimeCatalogSource {
    fun fetch(uri: URI, control: RuntimeControl): ByteArray
}

class RuntimeCatalogFetchException(
    val code: String,
    message: String,
    cause: Throwable? = null,
) : IOException(message, cause)

/** Loads signed catalogs from primary/mirror URLs and only caches verified bytes. */
class SignedRuntimeCatalogLoader(
    private val source: RuntimeCatalogSource,
    private val verifier: RuntimeCatalogSignatureVerifier = RuntimeCatalogSignatureVerifier(),
    private val cachePath: Path,
    private val maxCatalogBytes: Int = RuntimeCatalogCodec.MAX_ENCODED_BYTES,
) {
    init {
        require(maxCatalogBytes > 0) { "Catalog cache size limit must be positive" }
        require(cachePath.fileName != null) { "Catalog cache path must name a file" }
    }

    fun load(
        primary: URI,
        mirrors: List<URI> = emptyList(),
        control: RuntimeControl = RuntimeControl(),
    ): RuntimeCatalogLoadResult {
        val diagnostics = mutableListOf<RuntimeDiagnostic>()
        val candidates = listOf(primary) + mirrors.filter { it != primary }.distinct()
        candidates.forEachIndexed { index, uri ->
            val fetched = fetchAndVerify(uri, control)
            if (fetched.document != null) {
                    val sourceKind = if (index == 0) RuntimeCatalogLoadSource.PRIMARY else RuntimeCatalogLoadSource.MIRROR
                val cacheDiagnostics: List<RuntimeDiagnostic> = runCatching { writeCache(fetched.bytes!!) }
                    .fold(
                        onSuccess = { emptyList() },
                        onFailure = { listOf(diagnostic(RuntimeDiagnosticCode.CATALOG_DISK_ERROR, "CATALOG_CACHE", "Unable to persist verified runtime catalog", it)) },
                    )
                return RuntimeCatalogLoadResult(true, fetched.document, sourceKind, fetched.diagnostics + cacheDiagnostics, fetched.trustedCatalog)
            }
            diagnostics += fetched.diagnostics
        }

        val cached = readAndVerifyCache(control)
        if (cached.document != null) {
            return RuntimeCatalogLoadResult(true, cached.document, RuntimeCatalogLoadSource.CACHE, diagnostics + cached.diagnostics, cached.trustedCatalog)
        }
        return RuntimeCatalogLoadResult(false, null, RuntimeCatalogLoadSource.NONE, diagnostics + cached.diagnostics)
    }

    private data class VerifiedBytes(
        val document: RuntimeCatalogDocument?,
        val trustedCatalog: VerifiedRuntimeCatalog? = null,
        val bytes: ByteArray? = null,
        val diagnostics: List<RuntimeDiagnostic> = emptyList(),
    )

    private fun fetchAndVerify(uri: URI, control: RuntimeControl): VerifiedBytes {
        return try {
            control.checkpoint("CATALOG_FETCH")
            val bytes = source.fetch(uri, control)
            require(bytes.size <= maxCatalogBytes) { "Runtime catalog exceeds the configured size limit" }
            val envelope = runCatching { SignedRuntimeCatalogCodec.decode(bytes) }
                .getOrElse { throw RuntimeCatalogFetchException("PARSE_INVALID", "Invalid signed runtime catalog", it) }
            val verification = verifier.verify(envelope)
            if (verification.valid) {
                VerifiedBytes(verification.document, verification.trustedCatalog, bytes, verification.diagnostics)
            }
            else VerifiedBytes(null, diagnostics = verification.diagnostics.map { it.copy(details = it.details + ("uri" to uri.toString())) })
        }
        catch (error: RuntimeCatalogFetchException) {
            VerifiedBytes(null, diagnostics = listOf(diagnostic(mapCatalogCode(error.code), "CATALOG_FETCH", error.message ?: "Runtime catalog fetch failed", error)))
        }
        catch (error: RuntimeInstallException) {
            val code = if (error.stage.endsWith("CANCELLED")) RuntimeDiagnosticCode.CATALOG_CANCELLED
            else RuntimeDiagnosticCode.CATALOG_TIMEOUT
            VerifiedBytes(null, diagnostics = listOf(diagnostic(code, "CATALOG_FETCH", error.message ?: "Runtime catalog fetch stopped", error)))
        }
        catch (error: IllegalArgumentException) {
            val code = if (error.message?.contains("size limit", ignoreCase = true) == true) {
                RuntimeDiagnosticCode.CATALOG_TOO_LARGE
            }
            else RuntimeDiagnosticCode.CATALOG_PARSE_INVALID
            VerifiedBytes(null, diagnostics = listOf(diagnostic(code, "CATALOG_FETCH", error.message ?: "Invalid runtime catalog", error)))
        }
        catch (error: Exception) {
            VerifiedBytes(null, diagnostics = listOf(diagnostic(RuntimeDiagnosticCode.CATALOG_NETWORK_ERROR, "CATALOG_FETCH", "Unable to fetch runtime catalog", error)))
        }
    }

    private fun readAndVerifyCache(control: RuntimeControl): VerifiedBytes {
        if (!Files.isRegularFile(cachePath, LinkOption.NOFOLLOW_LINKS)) {
            return VerifiedBytes(null, diagnostics = listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.CATALOG_CACHE_INVALID, "CATALOG_CACHE", "No verified runtime catalog cache is available")))
        }
        return try {
            control.checkpoint("CATALOG_CACHE")
            val size = Files.size(cachePath)
            require(size in 1..maxCatalogBytes) { "Runtime catalog cache exceeds the configured size limit" }
            val bytes = Files.readAllBytes(cachePath)
            val envelope = SignedRuntimeCatalogCodec.decode(bytes)
            val verification = verifier.verify(envelope)
            if (verification.valid) {
                VerifiedBytes(verification.document, verification.trustedCatalog, bytes, verification.diagnostics)
            }
            else VerifiedBytes(null, diagnostics = verification.diagnostics.map { it.copy(code = RuntimeDiagnosticCode.CATALOG_CACHE_INVALID, stage = "CATALOG_CACHE") })
        }
        catch (error: Exception) {
            VerifiedBytes(null, diagnostics = listOf(diagnostic(RuntimeDiagnosticCode.CATALOG_CACHE_INVALID, "CATALOG_CACHE", "Runtime catalog cache is invalid", error)))
        }
    }

    private fun writeCache(bytes: ByteArray) {
        require(bytes.size <= maxCatalogBytes) { "Runtime catalog exceeds the configured size limit" }
        val parent = cachePath.toAbsolutePath().normalize().parent ?: error("Catalog cache path must have a parent")
        ensureNoSymlinkChain(parent)
        Files.createDirectories(parent)
        val temporary = parent.resolve(".${cachePath.fileName}.${UUID.randomUUID()}.tmp")
        try {
            Files.write(temporary, bytes, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
            java.nio.channels.FileChannel.open(temporary, StandardOpenOption.WRITE).use { it.force(true) }
            try {
                Files.move(temporary, cachePath, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            }
            catch (_: java.nio.file.AtomicMoveNotSupportedException) {
                Files.move(temporary, cachePath, StandardCopyOption.REPLACE_EXISTING)
            }
        }
        finally {
            Files.deleteIfExists(temporary)
        }
    }

    private fun diagnostic(code: RuntimeDiagnosticCode, stage: String, message: String, cause: Throwable? = null) =
        RuntimeDiagnostic(code, stage, message, causeType = cause?.javaClass?.name)

    private fun mapCatalogCode(code: String): RuntimeDiagnosticCode = when (code.uppercase()) {
        "TIMEOUT", "TIMED_OUT" -> RuntimeDiagnosticCode.CATALOG_TIMEOUT
        "CANCELLED" -> RuntimeDiagnosticCode.CATALOG_CANCELLED
        "DISK_ERROR" -> RuntimeDiagnosticCode.CATALOG_DISK_ERROR
        "PARSE_INVALID" -> RuntimeDiagnosticCode.CATALOG_PARSE_INVALID
        else -> RuntimeDiagnosticCode.CATALOG_NETWORK_ERROR
    }

    private fun ensureNoSymlinkChain(path: Path) {
        val absolute = path.toAbsolutePath().normalize()
        var current = absolute.root ?: error("Catalog cache path must have a root")
        for (part in absolute) {
            current = current.resolve(part.toString())
            if (Files.isSymbolicLink(current)) error("Catalog cache path contains a symbolic link: $current")
        }
    }
}

/** JDK-only source with optional HTTP proxy; it never accepts an HTTP catalog. */
class JdkRuntimeCatalogSource(
    proxySelector: ProxySelector? = null,
    private val requestTimeout: Duration = Duration.ofMinutes(5),
    private val maxCatalogBytes: Int = RuntimeCatalogCodec.MAX_ENCODED_BYTES,
) : RuntimeCatalogSource {
    private val client: HttpClient = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(30))
        .apply { proxySelector?.let { proxy(it) } }
        .build()

    override fun fetch(uri: URI, control: RuntimeControl): ByteArray {
        require(uri.scheme.equals("https", ignoreCase = true)) { "Runtime catalogs must use HTTPS" }
        control.checkpoint("CATALOG_HTTP")
        val request = HttpRequest.newBuilder(uri)
            .timeout(requestTimeout)
            .header("Accept", "application/octet-stream")
            .GET()
            .build()
        val response = try {
            client.send(request, HttpResponse.BodyHandlers.ofByteArray())
        }
        catch (error: Exception) {
            throw RuntimeCatalogFetchException("NETWORK_ERROR", "Unable to fetch runtime catalog", error)
        }
        control.checkpoint("CATALOG_HTTP")
        if (!response.uri().scheme.equals("https", ignoreCase = true)) {
            throw RuntimeCatalogFetchException("NETWORK_ERROR", "Runtime catalog redirected to an insecure URL")
        }
        if (response.statusCode() !in 200..299) {
            throw RuntimeCatalogFetchException("NETWORK_ERROR", "Runtime catalog returned HTTP ${response.statusCode()}")
        }
        if (response.body().size > maxCatalogBytes) {
            throw RuntimeCatalogFetchException("TOO_LARGE", "Runtime catalog exceeds the configured size limit")
        }
        return response.body()
    }
}
