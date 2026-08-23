package com.starnotesxj.sagemath.runtime

import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.attribute.PosixFileAttributeView

/** Structured verification result suitable for a Settings/SDK UI. */
data class RuntimeVerificationReport(
    val valid: Boolean,
    val problems: List<String> = emptyList(),
) {
    companion object {
        fun valid(): RuntimeVerificationReport = RuntimeVerificationReport(true)

        fun invalid(vararg problems: String): RuntimeVerificationReport =
            RuntimeVerificationReport(false, problems.toList())
    }
}

interface RuntimeManifestVerifier {
    fun verify(root: Path, manifest: RuntimeManifest): RuntimeVerificationReport
}

class FileRuntimeManifestVerifier(
    private val checksumVerifier: ChecksumVerifier = Sha256ChecksumVerifier(),
) : RuntimeManifestVerifier {
    override fun verify(root: Path, manifest: RuntimeManifest): RuntimeVerificationReport {
        val problems = mutableListOf<String>()
        val normalizedRoot = root.toAbsolutePath().normalize()
        if (Files.isSymbolicLink(root) || !Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
            return RuntimeVerificationReport.invalid("Runtime installation root is missing or symbolic")
        }

        val manifestPaths = manifest.files.map { it.path }.toSet()
        for (record in manifest.files) {
            val path = normalizedRoot.resolve(record.path).normalize()
            if (!path.startsWith(normalizedRoot) || Files.isSymbolicLink(path)) {
                problems += "Manifest path escapes runtime root: ${record.path}"
                continue
            }
            if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                problems += "Manifest file is missing: ${record.path}"
                continue
            }
            val actualSize = Files.size(path)
            if (actualSize != record.sizeBytes) {
                problems += "Manifest file size mismatch: ${record.path}"
                continue
            }
            if (!checksumVerifier.verify(path, record.sha256)) {
                problems += "Manifest file digest mismatch: ${record.path}"
            }
        }

        Files.walk(normalizedRoot).use { stream ->
            stream.forEach { path ->
                if (path == normalizedRoot) return@forEach
                val relative = normalizedRoot.relativize(path).toString().replace('\\', '/')
                if (Files.isSymbolicLink(path)) {
                    problems += "Unexpected symbolic link: $relative"
                }
                else if (Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) {
                    if (relative !in manifestPaths) {
                        problems += "Unexpected runtime file: $relative"
                    }
                }
                else if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) {
                    problems += "Unexpected runtime filesystem entry: $relative"
                }
            }
        }

        val executable = normalizedRoot.resolve(manifest.executable).normalize()
        if (!executable.startsWith(normalizedRoot) || Files.isSymbolicLink(executable) || !Files.isRegularFile(executable, LinkOption.NOFOLLOW_LINKS)) {
            problems += "Manifest executable is missing: ${manifest.executable}"
        }
        else if (
            manifest.runtimeId.platform.os != OperatingSystem.WINDOWS &&
            Files.getFileAttributeView(executable, PosixFileAttributeView::class.java) != null &&
            !Files.isExecutable(executable)
        ) {
            problems += "Manifest executable is not executable: ${manifest.executable}"
        }

        manifest.pythonExecutable?.let { pythonRelative ->
            val python = normalizedRoot.resolve(pythonRelative).normalize()
            if (
                !python.startsWith(normalizedRoot) ||
                Files.isSymbolicLink(python) ||
                !Files.isRegularFile(python, LinkOption.NOFOLLOW_LINKS)
            ) {
                problems += "Manifest Python executable is missing: $pythonRelative"
            }
            else if (
                manifest.runtimeId.platform.os != OperatingSystem.WINDOWS &&
                Files.getFileAttributeView(python, PosixFileAttributeView::class.java) != null &&
                !Files.isExecutable(python)
            ) {
                problems += "Manifest Python executable is not executable: $pythonRelative"
            }
        }

        return if (problems.isEmpty()) {
            RuntimeVerificationReport.valid()
        }
        else {
            RuntimeVerificationReport(false, problems)
        }
    }
}

interface RuntimeLocator {
    fun locate(root: Path, id: SageRuntimeId): InstalledRuntime?
}

class FileRuntimeLocator(
    private val manifestVerifier: RuntimeManifestVerifier = FileRuntimeManifestVerifier(),
) : RuntimeLocator {
    override fun locate(root: Path, id: SageRuntimeId): InstalledRuntime? {
        val normalizedRoot = root.toAbsolutePath().normalize()
        if (Files.isSymbolicLink(root) || !Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) return null
        val versionsRoot = normalizedRoot.resolve("versions")
        if (Files.isSymbolicLink(versionsRoot) || !Files.isDirectory(versionsRoot, LinkOption.NOFOLLOW_LINKS)) return null
        val currentPath = normalizedRoot.resolve("current")
        val currentName = currentPath
            .takeIf { !Files.isSymbolicLink(it) && Files.isRegularFile(it, LinkOption.NOFOLLOW_LINKS) }
            ?.let { runCatching { Files.readString(it).trim() }.getOrNull() }
            ?.takeIf { it.length <= 128 && RuntimeArtifact.isSafeRelativePath(it) && !it.contains('/') && !it.contains('\\') }
            ?: return null
        val runtimeRoot = versionsRoot.resolve(currentName).normalize()
        if (
            !runtimeRoot.startsWith(versionsRoot) ||
            Files.isSymbolicLink(runtimeRoot) ||
            !Files.isDirectory(runtimeRoot, LinkOption.NOFOLLOW_LINKS)
        ) return null
        val marker = versionsRoot.resolve(".$currentName.meta")
        if (Files.isSymbolicLink(marker) || !Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS)) return null
        val manifest = runCatching {
            val size = Files.size(marker)
            require(size in 1..RuntimeManifestCodec.MAX_ENCODED_BYTES) { "Runtime manifest sidecar is too large" }
            RuntimeManifestCodec.decode(Files.readAllBytes(marker))
        }.getOrNull() ?: return null
        if (manifest.runtimeId != id || !id.isValidInstalledDirectoryName(currentName)) return null
        val executable = runtimeRoot.resolve(manifest.executable).normalize()
        if (
            !executable.startsWith(runtimeRoot) ||
            Files.isSymbolicLink(executable) ||
            !Files.isRegularFile(executable, LinkOption.NOFOLLOW_LINKS)
        ) return null
        if (!manifestVerifier.verify(runtimeRoot, manifest).valid) return null
        return InstalledRuntime(id, runtimeRoot, executable, Files.getLastModifiedTime(runtimeRoot).toInstant(), manifest)
    }
}

/**
 * Small product-facing facade. IntelliJ adapters can run these calls off the
 * UI thread and expose progress/cancellation through the existing interfaces.
 */
class SageRuntimeManager(
    private val catalog: RuntimeCatalog,
    private val installer: RuntimeInstaller,
    private val locator: RuntimeLocator,
    private val installRoot: Path,
) {
    fun available(query: RuntimeQuery = RuntimeQuery()): List<RuntimeArtifact> = catalog.list(query)

    fun install(
        artifact: RuntimeArtifact,
        manifest: RuntimeManifest,
        progress: DownloadProgressListener = NoopDownloadProgress,
        cancellation: InstallationCancellation = NeverCancelled,
        replaceExisting: Boolean = false,
    ): InstallResult = installer.install(
        RuntimeInstallRequest(
            artifact = artifact,
            installRoot = installRoot,
            manifest = manifest,
            progress = progress,
            cancellation = cancellation,
            replaceExisting = replaceExisting,
        )
    )

    fun locate(id: SageRuntimeId): InstalledRuntime? = locator.locate(installRoot, id)

    fun current(id: SageRuntimeId): InstalledRuntime? = locate(id)
}
