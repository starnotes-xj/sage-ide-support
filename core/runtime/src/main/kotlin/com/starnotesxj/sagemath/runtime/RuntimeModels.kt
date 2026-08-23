package com.starnotesxj.sagemath.runtime

import java.net.URI
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.attribute.PosixFileAttributeView
import java.text.Normalizer
import java.security.MessageDigest
import java.time.Instant
import java.util.Locale

/** Supported host operating-system families for managed SageMath packages. */
enum class OperatingSystem {
    WINDOWS,
    MACOS,
    LINUX,
    UNKNOWN,
}

enum class CpuArchitecture {
    X64,
    ARM64,
    ARM,
    X86,
    UNKNOWN,
}

enum class Libc {
    GLIBC,
    MUSL,
    UNKNOWN,
}

data class PlatformTriple(
    val os: OperatingSystem,
    val architecture: CpuArchitecture,
    val libc: Libc? = null,
) {
    override fun toString(): String = buildString {
        append(os.name.lowercase())
        append('-')
        append(architecture.name.lowercase())
        libc?.let {
            append('-')
            append(it.name.lowercase())
        }
    }
}

/** Runtime platform detection is kept injectable for deterministic tests. */
object PlatformDetector {
    fun detect(
        osName: String = System.getProperty("os.name", ""),
        osArch: String = System.getProperty("os.arch", ""),
    ): PlatformTriple {
        val os = when {
            osName.contains("win", ignoreCase = true) -> OperatingSystem.WINDOWS
            osName.contains("mac", ignoreCase = true) || osName.contains("darwin", ignoreCase = true) -> OperatingSystem.MACOS
            osName.contains("nux", ignoreCase = true) || osName.contains("linux", ignoreCase = true) -> OperatingSystem.LINUX
            else -> OperatingSystem.UNKNOWN
        }
        val architecture = when (osArch.lowercase()) {
            "amd64", "x86_64", "x64" -> CpuArchitecture.X64
            "aarch64", "arm64" -> CpuArchitecture.ARM64
            "arm", "arm32", "armv7", "armv7l" -> CpuArchitecture.ARM
            "x86", "i386", "i486", "i586", "i686" -> CpuArchitecture.X86
            else -> CpuArchitecture.UNKNOWN
        }
        return PlatformTriple(os = os, architecture = architecture)
    }
}

data class SageRuntimeId(
    val version: String,
    val platform: PlatformTriple,
    val distribution: String = "managed",
) {
    init {
        require(version.isNotBlank()) { "SageMath version must not be blank" }
        require(distribution.isNotBlank()) { "Runtime distribution must not be blank" }
    }

    /** Stable, collision-resistant path component; never use a remote filename as a key. */
    fun stableName(): String {
        val canonical = listOf(distribution, version, platform.toString())
            .joinToString("\u0000")
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(canonical.toByteArray(StandardCharsets.UTF_8))
            .joinToString("") { "%02x".format(Locale.ROOT, it) }
        return "runtime-${digest.take(24)}"
    }

    /** Accept only the immutable directory name or the installer's UUID suffix. */
    fun isValidInstalledDirectoryName(name: String): Boolean {
        if (name == stableName()) return true
        val suffix = name.removePrefix("${stableName()}-")
        return suffix != name && UUID_SUFFIX.matches(suffix)
    }

    companion object {
        private val UUID_SUFFIX = Regex("[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
    }
}

enum class ArchiveFormat {
    ZIP,
    TAR_GZ,
}

data class RuntimeArtifact(
    val id: SageRuntimeId,
    val uri: URI,
    val archiveFormat: ArchiveFormat,
    val sizeBytes: Long? = null,
    val sha256: String,
    val entrypoint: String = if (id.platform.os == OperatingSystem.WINDOWS) "sage.exe" else "sage",
    val manifestUri: URI? = null,
    val publishedAt: Instant? = null,
    val metadata: Map<String, String> = emptyMap(),
) {
    init {
        require(uri.scheme.equals("https", ignoreCase = true)) {
            "Managed SageMath artifacts must use HTTPS"
        }
        require(sizeBytes == null || sizeBytes >= 0) { "Artifact size must not be negative" }
        require(sha256.matches(SHA256_PATTERN)) { "SHA-256 must be exactly 64 hexadecimal characters" }
        require(isSafeRelativePath(entrypoint)) { "Runtime entrypoint must be a safe relative path" }
        require(entrypoint.none { it.isISOControl() }) { "Runtime entrypoint contains a control character" }
        metadata[BUNDLED_PYTHON_METADATA_KEY]?.let { pythonExecutable ->
            require(pythonExecutable.isNotBlank()) { "Bundled Python executable metadata must not be blank" }
            require(isSafeRelativePath(pythonExecutable)) {
                "Bundled Python executable must be a safe path relative to the runtime root"
            }
            require(pythonExecutable.none { it.isISOControl() }) {
                "Bundled Python executable contains a control character"
            }
        }
        manifestUri?.let {
            require(it.scheme.equals("https", ignoreCase = true)) {
                "Runtime manifests must use HTTPS"
            }
        }
    }

    companion object {
        private val SHA256_PATTERN = Regex("[0-9a-fA-F]{64}")

        fun isSafeRelativePath(value: String): Boolean {
            if (value.isBlank() || value != Normalizer.normalize(value, Normalizer.Form.NFC)) return false
            if (value.startsWith("/") || value.startsWith("\\")) return false
            if (Regex("^[A-Za-z]:.*").matches(value)) return false
            val parts = value.replace('\\', '/').split('/')
            return parts.all(::isSafePathComponent)
        }

        private fun isSafePathComponent(component: String): Boolean {
            if (component.isBlank() || component != Normalizer.normalize(component, Normalizer.Form.NFC)) return false
            if (component == "." || component == "..") return false
            if (component.any { it.isISOControl() || it in "\\/:*?\"<>|" }) return false
            if (component.trimEnd('.', ' ') != component) return false
            val deviceName = component.substringBefore('.').uppercase(Locale.ROOT)
            if (deviceName in WINDOWS_DEVICE_NAMES) return false
            return true
        }

        const val BUNDLED_PYTHON_METADATA_KEY: String = "runtime.pythonExecutable"

        private val WINDOWS_DEVICE_NAMES = buildSet {
            addAll(listOf("CON", "PRN", "AUX", "NUL"))
            for (index in 1..9) {
                add("COM$index")
                add("LPT$index")
            }
        }
    }
}

data class RuntimeQuery(
    val version: String? = null,
    val platform: PlatformTriple = PlatformDetector.detect(),
    val distribution: String? = null,
)

interface RuntimeCatalog {
    fun list(query: RuntimeQuery = RuntimeQuery()): List<RuntimeArtifact>

    fun resolve(id: SageRuntimeId): RuntimeArtifact? = list(RuntimeQuery(
        version = id.version,
        platform = id.platform,
        distribution = id.distribution,
    )).firstOrNull { it.id == id }
}

class StaticRuntimeCatalog(artifacts: List<RuntimeArtifact>) : RuntimeCatalog {
    private val entries = artifacts.toList()

    override fun list(query: RuntimeQuery): List<RuntimeArtifact> = entries
        .asSequence()
        .filter { query.version == null || it.id.version == query.version }
        .filter { it.id.platform == query.platform }
        .filter { query.distribution == null || it.id.distribution == query.distribution }
        .sortedByDescending { it.publishedAt }
        .toList()
}

/** A file-level lock/verification manifest produced by the installer. */
data class RuntimeFileRecord(
    val path: String,
    val sizeBytes: Long,
    val sha256: String,
) {
    init {
        require(path == path.replace('\\', '/')) { "Manifest path must use forward slashes: $path" }
        require(RuntimeArtifact.isSafeRelativePath(path)) { "Manifest path is unsafe: $path" }
        require(path.none { it.isISOControl() }) { "Manifest path contains a control character" }
        require(sizeBytes >= 0) { "Manifest file size must not be negative" }
        require(sha256.matches(Regex("[0-9a-fA-F]{64}"))) {
            "Manifest SHA-256 must be exactly 64 hexadecimal characters"
        }
    }
}

data class RuntimeManifest(
    val schemaVersion: Int,
    val runtimeId: SageRuntimeId,
    val executable: String,
    val files: List<RuntimeFileRecord>,
    val artifactSha256: String,
    val generatedAt: Instant = Instant.now(),
    val sageVersion: String = runtimeId.version,
    val pythonVersion: String? = null,
    /** Relative path of the Python interpreter bundled by this SageMath runtime. */
    val pythonExecutable: String? = null,
) {
    /** Resolves the declared interpreter only when it is still inside this runtime root. */
    fun resolvePythonExecutable(root: Path): Path? = pythonExecutable?.let { relative ->
        val normalizedRoot = root.toAbsolutePath().normalize()
        val candidate = normalizedRoot.resolve(relative).normalize()
        candidate.takeIf {
            it.startsWith(normalizedRoot) &&
                !Files.isSymbolicLink(it) &&
                Files.isRegularFile(it, LinkOption.NOFOLLOW_LINKS) &&
                (runtimeId.platform.os == OperatingSystem.WINDOWS || hasPosixExecuteBit(it))
        }
    }

    private fun hasPosixExecuteBit(path: Path): Boolean =
        Files.getFileAttributeView(path, PosixFileAttributeView::class.java) == null || Files.isExecutable(path)

    init {
        require(schemaVersion == 1) { "Unsupported runtime manifest schema: $schemaVersion" }
        require(artifactSha256.matches(Regex("[0-9a-fA-F]{64}"))) {
            "Manifest artifact SHA-256 must be exactly 64 hexadecimal characters"
        }
        require(RuntimeArtifact.isSafeRelativePath(executable)) { "Manifest executable is unsafe" }
        require(executable.none { it.isISOControl() }) { "Manifest executable contains a control character" }
        pythonExecutable?.let { path ->
            require(RuntimeArtifact.isSafeRelativePath(path)) { "Manifest Python executable is unsafe" }
            require(path.none { it.isISOControl() }) { "Manifest Python executable contains a control character" }
        }
        require(files.map { it.path }.toSet().size == files.size) { "Manifest contains duplicate file paths" }
        val normalizedPaths = files.map { it.path.lowercase(Locale.ROOT) }
        require(normalizedPaths.toSet().size == files.size) {
            "Manifest contains case-colliding file paths"
        }
        require(sageVersion == runtimeId.version) { "Manifest SageMath version must match the runtime id" }
        val filePaths = files.map { it.path }.toSet()
        require(executable in filePaths) { "Manifest executable must be included in files" }
        require(pythonExecutable == null || pythonExecutable in filePaths) {
            "Manifest Python executable must be included in files"
        }
    }
}
