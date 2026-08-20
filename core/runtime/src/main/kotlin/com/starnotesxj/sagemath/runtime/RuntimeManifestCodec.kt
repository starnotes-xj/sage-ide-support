package com.starnotesxj.sagemath.runtime

import java.nio.charset.StandardCharsets
import java.time.Instant
import java.util.Base64

/**
 * Small dependency-free sidecar format for installed manifests.
 *
 * The remote catalog may later use signed JSON, but the local immutable
 * version directory needs a deterministic format that can be read before the
 * IntelliJ adapter is available. Values are URL-safe base64 encoded so path,
 * version, and distribution text cannot break the record grammar.
 */
object RuntimeManifestCodec {
    const val MAX_ENCODED_BYTES = 16 * 1024 * 1024
    private const val MAX_FILE_RECORDS = 250_000
    private const val MAX_LINE_LENGTH = 4096
    private const val SCHEMA_VERSION = "schemaVersion"
    private const val RUNTIME_VERSION = "runtimeVersion"
    private const val RUNTIME_DISTRIBUTION = "runtimeDistribution"
    private const val RUNTIME_OS = "runtimeOs"
    private const val RUNTIME_ARCHITECTURE = "runtimeArchitecture"
    private const val RUNTIME_LIBC = "runtimeLibc"
    private const val ARTIFACT_SHA256 = "artifactSha256"
    private const val EXECUTABLE = "executable"
    private const val GENERATED_AT = "generatedAt"
    private const val SAGE_VERSION = "sageVersion"
    private const val PYTHON_VERSION = "pythonVersion"
    private const val FILE = "file"

    fun encode(manifest: RuntimeManifest): ByteArray = buildString {
        appendLine("$SCHEMA_VERSION=${manifest.schemaVersion}")
        appendLine("$RUNTIME_VERSION=${encodeValue(manifest.runtimeId.version)}")
        appendLine("$RUNTIME_DISTRIBUTION=${encodeValue(manifest.runtimeId.distribution)}")
        appendLine("$RUNTIME_OS=${manifest.runtimeId.platform.os.name}")
        appendLine("$RUNTIME_ARCHITECTURE=${manifest.runtimeId.platform.architecture.name}")
        appendLine("$RUNTIME_LIBC=${manifest.runtimeId.platform.libc?.name.orEmpty()}")
        appendLine("$ARTIFACT_SHA256=${manifest.artifactSha256.lowercase()}")
        appendLine("$EXECUTABLE=${encodeValue(manifest.executable)}")
        appendLine("$GENERATED_AT=${manifest.generatedAt}")
        appendLine("$SAGE_VERSION=${encodeValue(manifest.sageVersion)}")
        appendLine("$PYTHON_VERSION=${manifest.pythonVersion?.let(::encodeValue).orEmpty()}")
        manifest.files.forEach { record ->
            appendLine("$FILE=${encodeValue(record.path)}|${record.sizeBytes}|${record.sha256.lowercase()}")
        }
    }.toByteArray(StandardCharsets.UTF_8)

    fun decode(bytes: ByteArray): RuntimeManifest = decode(bytes.toString(StandardCharsets.UTF_8))

    fun decode(text: String): RuntimeManifest {
        val values = linkedMapOf<String, String>()
        val files = mutableListOf<RuntimeFileRecord>()
        require(text.toByteArray(StandardCharsets.UTF_8).size in 1..MAX_ENCODED_BYTES) {
            "Runtime manifest sidecar is too large"
        }
        text.lineSequence()
            .filter { it.isNotEmpty() }
            .forEach { line ->
                require(line.length <= MAX_LINE_LENGTH) { "Runtime manifest line is too long" }
                val separator = line.indexOf('=')
                require(separator > 0) { "Malformed runtime manifest line" }
                val key = line.substring(0, separator)
                val value = line.substring(separator + 1)
                if (key == FILE) {
                    require(files.size < MAX_FILE_RECORDS) { "Runtime manifest contains too many files" }
                    val parts = value.split('|')
                    require(parts.size == 3) { "Malformed runtime manifest file record" }
                        files += RuntimeFileRecord(
                        path = decodeValue(parts[0]),
                        sizeBytes = parts[1].toLongOrNull() ?: error("Invalid runtime manifest file size"),
                        sha256 = parts[2],
                    )
                }
                else {
                    require(values.put(key, value) == null) { "Duplicate runtime manifest field: $key" }
                }
            }

        val unknownFields = values.keys - setOf(
            SCHEMA_VERSION,
            RUNTIME_VERSION,
            RUNTIME_DISTRIBUTION,
            RUNTIME_OS,
            RUNTIME_ARCHITECTURE,
            RUNTIME_LIBC,
            ARTIFACT_SHA256,
            EXECUTABLE,
            GENERATED_AT,
            SAGE_VERSION,
            PYTHON_VERSION,
        )
        require(unknownFields.isEmpty()) { "Unknown runtime manifest fields: $unknownFields" }
        val required: (String) -> String = { key -> values[key] ?: error("Missing runtime manifest field: $key") }
        val os = enumValue<OperatingSystem>(required(RUNTIME_OS), RUNTIME_OS)
        val architecture = enumValue<CpuArchitecture>(required(RUNTIME_ARCHITECTURE), RUNTIME_ARCHITECTURE)
        val libc = required(RUNTIME_LIBC).takeIf { it.isNotEmpty() }?.let { enumValue<Libc>(it, RUNTIME_LIBC) }
        return RuntimeManifest(
            schemaVersion = required(SCHEMA_VERSION).toIntOrNull() ?: error("Invalid runtime manifest schema"),
            runtimeId = SageRuntimeId(
                version = decodeValue(required(RUNTIME_VERSION)),
                platform = PlatformTriple(os, architecture, libc),
                distribution = decodeValue(required(RUNTIME_DISTRIBUTION)),
            ),
            artifactSha256 = required(ARTIFACT_SHA256),
            executable = decodeValue(required(EXECUTABLE)),
            files = files,
            generatedAt = runCatching { Instant.parse(required(GENERATED_AT)) }
                .getOrElse { error("Invalid runtime manifest timestamp") },
            sageVersion = decodeValue(required(SAGE_VERSION)),
            pythonVersion = required(PYTHON_VERSION).takeIf { it.isNotEmpty() }?.let(::decodeValue),
        )
    }

    private fun encodeValue(value: String): String = Base64.getUrlEncoder()
        .withoutPadding()
        .encodeToString(value.toByteArray(StandardCharsets.UTF_8))

    private fun decodeValue(value: String): String = runCatching {
        Base64.getUrlDecoder().decode(value).toString(StandardCharsets.UTF_8)
    }.getOrElse { error("Invalid encoded runtime manifest value") }

    private inline fun <reified T : Enum<T>> enumValue(value: String, field: String): T =
        runCatching { enumValueOf<T>(value) }.getOrElse { error("Invalid runtime manifest $field") }
}
