package com.starnotesxj.sagemath.runtime

import java.io.BufferedInputStream
import java.io.IOException
import java.io.InputStream
import java.nio.channels.FileChannel
import java.nio.channels.FileLock
import java.nio.channels.OverlappingFileLockException
import java.util.concurrent.TimeUnit
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.nio.file.attribute.PosixFileAttributeView
import java.nio.file.attribute.PosixFilePermission
import java.security.MessageDigest
import java.time.Instant
import java.util.UUID
import java.util.zip.ZipInputStream

fun interface DownloadProgressListener {
    fun onProgress(bytesRead: Long, totalBytes: Long?)
}

fun interface InstallationCancellation {
    fun isCancelled(): Boolean
}

object NoopDownloadProgress : DownloadProgressListener {
    override fun onProgress(bytesRead: Long, totalBytes: Long?) = Unit
}

object NeverCancelled : InstallationCancellation {
    override fun isCancelled(): Boolean = false
}

data class DownloadedArtifact(
    val path: Path,
    val bytes: Long,
    val sha256: String,
)

interface RuntimeDownloader {
    fun download(
        artifact: RuntimeArtifact,
        destination: Path,
        progress: DownloadProgressListener = NoopDownloadProgress,
        cancellation: InstallationCancellation = NeverCancelled,
        control: RuntimeControl = RuntimeControl(),
    ): DownloadedArtifact
}

interface ChecksumVerifier {
    fun sha256(path: Path): String

    fun verify(path: Path, expectedSha256: String): Boolean =
        sha256(path).equals(expectedSha256, ignoreCase = true)
}

class Sha256ChecksumVerifier : ChecksumVerifier {
    override fun sha256(path: Path): String {
        val digest = MessageDigest.getInstance("SHA-256")
        Files.newInputStream(path, StandardOpenOption.READ).use { input ->
            val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    companion object {
        private const val DEFAULT_BUFFER_SIZE = 64 * 1024
    }
}

class HttpRuntimeDownloader(
    private val connectionFactory: (RuntimeArtifact) -> InputStream,
    private val checksumVerifier: ChecksumVerifier = Sha256ChecksumVerifier(),
    private val maxDownloadBytes: Long = DEFAULT_MAX_DOWNLOAD_BYTES,
) : RuntimeDownloader {
    override fun download(
        artifact: RuntimeArtifact,
        destination: Path,
        progress: DownloadProgressListener,
        cancellation: InstallationCancellation,
        control: RuntimeControl,
    ): DownloadedArtifact {
        control.checkpoint("DOWNLOAD")
        require(maxDownloadBytes > 0) { "Maximum download size must be positive" }
        require(destination.parent != null) { "Download destination must have a parent directory" }
        ensureDownloadPathIsSafe(destination)
        var bytes = 0L
        try {
            Files.createDirectories(destination.parent!!)
            connectionFactory(artifact).use { raw ->
                BufferedInputStream(raw).use { input ->
                    Files.newOutputStream(
                        destination,
                        StandardOpenOption.CREATE_NEW,
                        StandardOpenOption.WRITE,
                    ).use { output ->
                        val buffer = ByteArray(64 * 1024)
                        while (true) {
                            control.checkpoint("DOWNLOAD")
                            if (cancellation.isCancelled()) {
                                throw RuntimeInstallException("DOWNLOAD_CANCELLED", "Runtime download was cancelled")
                            }
                            val read = input.read(buffer)
                            if (read < 0) break
                            bytes += read
                            if (bytes > maxDownloadBytes || artifact.sizeBytes?.let { bytes > it } == true) {
                                throw RuntimeInstallException("DOWNLOAD_TOO_LARGE", "Runtime artifact exceeds the configured size limit")
                            }
                            output.write(buffer, 0, read)
                            progress.onProgress(bytes, artifact.sizeBytes)
                        }
                    }
                }
            }
        }
        catch (error: Exception) {
            Files.deleteIfExists(destination)
            throw error
        }
        if (artifact.sizeBytes != null && bytes != artifact.sizeBytes) {
            Files.deleteIfExists(destination)
            throw RuntimeInstallException("DOWNLOAD_SIZE_MISMATCH", "Downloaded runtime size does not match the catalog")
        }
        val actualSha256 = try {
            checksumVerifier.sha256(destination)
        }
        catch (error: Exception) {
            Files.deleteIfExists(destination)
            throw error
        }
        if (!actualSha256.equals(artifact.sha256, ignoreCase = true)) {
            Files.deleteIfExists(destination)
            throw RuntimeInstallException("DIGEST_MISMATCH", "Downloaded runtime digest does not match the catalog")
        }
        return DownloadedArtifact(destination, bytes, actualSha256)
    }

    companion object {
        const val DEFAULT_MAX_DOWNLOAD_BYTES = 16L * 1024 * 1024 * 1024
    }
}

data class RuntimeInstallRequest(
    val artifact: RuntimeArtifact,
    val installRoot: Path,
    val manifest: RuntimeManifest,
    val progress: DownloadProgressListener = NoopDownloadProgress,
    val cancellation: InstallationCancellation = NeverCancelled,
    val replaceExisting: Boolean = false,
    /** Optional monotonic deadline and cancellation propagated through installation. */
    val control: RuntimeControl = RuntimeControl(),
) {
    init {
        require(manifest.runtimeId == artifact.id) { "Runtime manifest does not match the artifact" }
        require(manifest.artifactSha256.equals(artifact.sha256, ignoreCase = true)) {
            "Runtime manifest digest does not match the artifact"
        }
        require(manifest.executable == artifact.entrypoint) { "Runtime manifest executable does not match the artifact" }
        val artifactPython = artifact.metadata[RuntimeArtifact.BUNDLED_PYTHON_METADATA_KEY]
        require(artifactPython == null || artifactPython == manifest.pythonExecutable) {
            "Runtime manifest bundled Python executable does not match the artifact"
        }
    }
}

data class InstalledRuntime(
    val id: SageRuntimeId,
    val root: Path,
    val executable: Path,
    val verifiedAt: Instant,
    val manifest: RuntimeManifest? = null,
) {
    /** The verified Python interpreter shipped by SageMath, if declared by the manifest. */
    val pythonExecutable: Path?
        get() = manifest?.resolvePythonExecutable(root)
}

sealed interface InstallResult {
    data class Installed(val runtime: InstalledRuntime) : InstallResult
    data class AlreadyInstalled(val runtime: InstalledRuntime) : InstallResult
    data class Failed(
        val stage: String,
        val cause: Throwable,
        val cleanupPerformed: Boolean,
    ) : InstallResult
}

class RuntimeInstallException(
    val stage: String,
    message: String,
    cause: Throwable? = null,
) : IOException(message, cause)

interface RuntimeInstaller {
    fun install(request: RuntimeInstallRequest): InstallResult
}

/**
 * Installs immutable version directories and atomically updates a small
 * `current` pointer. Existing versions are never deleted during replacement.
 */
class ZipRuntimeInstaller(
    private val downloader: RuntimeDownloader,
    private val checksumVerifier: ChecksumVerifier = Sha256ChecksumVerifier(),
    private val manifestVerifier: RuntimeManifestVerifier = FileRuntimeManifestVerifier(checksumVerifier),
) : RuntimeInstaller {
    override fun install(request: RuntimeInstallRequest): InstallResult {
        if (request.artifact.archiveFormat != ArchiveFormat.ZIP) {
            return InstallResult.Failed(
                "ARCHIVE_FORMAT_UNSUPPORTED",
                RuntimeInstallException("ARCHIVE_FORMAT_UNSUPPORTED", "Only ZIP SageMath artifacts are supported"),
                cleanupPerformed = true,
            )
        }

        val runtimeId = request.artifact.id.stableName()
        val installRoot = request.installRoot.toAbsolutePath().normalize()
        val versionsRoot = installRoot.resolve("versions")
        val lockPath = installRoot.resolve(".$runtimeId.lock")
        val stagingDir = installRoot.resolve(".staging").resolve(UUID.randomUUID().toString())
        var cleanupPerformed = false

        return try {
            ensureDirectoryChainIsNotSymbolic(installRoot)
            Files.createDirectories(installRoot)
            ensureDirectoryChainIsNotSymbolic(installRoot.resolve("versions"))
            Files.createDirectories(versionsRoot)
            ensureDirectoryChainIsNotSymbolic(versionsRoot)
            controlCheckpoint(request.control, "INSTALL")
            FileChannel.open(
                lockPath,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE,
            ).use { lockChannel ->
                acquireLock(lockChannel, request.control).use {
                    val existing = existingRuntime(request, installRoot, versionsRoot)
                    if (existing != null && !request.replaceExisting) {
                        checkpoint(request, "INSTALL")
                        return InstallResult.AlreadyInstalled(existing)
                    }

                    ensureDirectoryChainIsNotSymbolic(stagingDir)
                    Files.createDirectories(stagingDir)
                    val archive = stagingDir.resolve("artifact.zip")
                    checkpoint(request, "DOWNLOAD")
                    val downloaded = downloader.download(request.artifact, archive, request.progress, request.cancellation, request.control)
                    checkpoint(request, "DOWNLOAD")
                    if (downloaded.path != archive || !checksumVerifier.verify(archive, request.artifact.sha256)) {
                        throw RuntimeInstallException("DIGEST_MISMATCH", "Runtime archive digest does not match the catalog")
                    }
                    val payload = stagingDir.resolve("payload")
                    Files.createDirectories(payload)
                    unzipSafely(archive, payload, request.cancellation, request.control)

                    val executable = payload.resolve(request.artifact.entrypoint).normalize()
                    if (
                        !executable.startsWith(payload) ||
                        Files.isSymbolicLink(executable) ||
                        !Files.isRegularFile(executable, LinkOption.NOFOLLOW_LINKS)
                    ) {
                        throw RuntimeInstallException("ENTRYPOINT_INVALID", "Runtime entrypoint is missing from the archive")
                    }
                    if (!request.artifact.platformIsWindows()) {
                        ensureUnixExecutable(executable)
                    }
                    checkpoint(request, "INSTALL")
                    val report = manifestVerifier.verify(payload, request.manifest)
                    if (!report.valid) {
                        throw RuntimeInstallException(
                            "MANIFEST_INVALID",
                            "Runtime manifest verification failed: ${report.problems.joinToString(", ")}",
                        )
                    }
                    checkpoint(request, "INSTALL")

                    val stagedRuntime = stagingDir.resolve("runtime")
                    moveDirectoryForPublication(payload, stagedRuntime)
                    forceDirectory(stagedRuntime)

                    val publishedName = "$runtimeId-${UUID.randomUUID()}"
                    val publishedDir = versionsRoot.resolve(publishedName)
                    moveDirectoryForPublication(stagedRuntime, publishedDir)
                    forceDirectory(publishedDir)
                    writeInstallMetadata(installRoot, publishedName, request)
                    updateCurrentPointer(installRoot, publishedName)

                    cleanupDirectory(stagingDir)
                    cleanupPerformed = true
                    InstallResult.Installed(
                        InstalledRuntime(
                            request.artifact.id,
                            publishedDir,
                            publishedDir.resolve(request.artifact.entrypoint),
                            Instant.now(),
                            request.manifest,
                        )
                    )
                }
            }
        }
        catch (error: Exception) {
            if (Files.exists(stagingDir)) {
                runCatching { cleanupDirectory(stagingDir) }
                    .onSuccess { cleanupPerformed = true }
            }
            InstallResult.Failed(
                stage = (error as? RuntimeInstallException)?.stage ?: "INSTALL",
                cause = error,
                cleanupPerformed = cleanupPerformed,
            )
        }
    }

    private fun existingRuntime(request: RuntimeInstallRequest, installRoot: Path, versionsRoot: Path): InstalledRuntime? {
        val currentName = readCurrentPointer(installRoot) ?: return null
        val runtimeId = request.artifact.id.stableName()
        if (currentName != runtimeId && !currentName.startsWith("$runtimeId-")) return null
        val runtimeDir = versionsRoot.resolve(currentName).normalize()
        if (
            !runtimeDir.startsWith(versionsRoot) ||
            Files.isSymbolicLink(runtimeDir) ||
            !Files.isDirectory(runtimeDir, LinkOption.NOFOLLOW_LINKS)
        ) return null
        val executable = runtimeDir.resolve(request.artifact.entrypoint).normalize()
        if (
            !executable.startsWith(runtimeDir) ||
            Files.isSymbolicLink(executable) ||
            !Files.isRegularFile(executable, LinkOption.NOFOLLOW_LINKS)
        ) return null
        val marker = versionsRoot.resolve(".$currentName.meta")
        if (Files.isSymbolicLink(marker) || !Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS)) return null
        val installedManifest = runCatching {
            val size = Files.size(marker)
            require(size in 1..RuntimeManifestCodec.MAX_ENCODED_BYTES) { "Runtime manifest sidecar is too large" }
            RuntimeManifestCodec.decode(Files.readAllBytes(marker))
        }.getOrNull() ?: return null
        if (installedManifest != request.manifest) return null
        val report = manifestVerifier.verify(runtimeDir, installedManifest)
        if (!report.valid) return null
        return InstalledRuntime(request.artifact.id, runtimeDir, executable, Instant.now(), installedManifest)
    }

    private fun readCurrentPointer(installRoot: Path): String? {
        val pointer = installRoot.resolve("current")
        if (Files.isSymbolicLink(pointer) || !Files.isRegularFile(pointer, LinkOption.NOFOLLOW_LINKS)) return null
        val value = runCatching {
            Files.size(pointer).takeIf { it in 1..128 } ?: return@runCatching null
            Files.readString(pointer).trim()
        }.getOrNull() ?: return null
        return value.takeIf {
            it.length <= 128 &&
                RuntimeArtifact.isSafeRelativePath(it) &&
                !it.contains('/') &&
                !it.contains('\\')
        }
    }

    private fun updateCurrentPointer(installRoot: Path, runtimeName: String) {
        val pointer = installRoot.resolve("current")
        val temporary = installRoot.resolve(".current-${UUID.randomUUID()}.tmp")
        Files.writeString(
            temporary,
            runtimeName,
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE,
        )
        forceFile(temporary)
        try {
            Files.move(temporary, pointer, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
        }
        catch (_: AtomicMoveNotSupportedException) {
            // The version directory is complete before this step. On file
            // systems without ATOMIC_MOVE, replacement is recoverable because
            // old version directories remain available for repair.
            Files.move(temporary, pointer, StandardCopyOption.REPLACE_EXISTING)
        }
    }

    private fun writeInstallMetadata(installRoot: Path, publishedName: String, request: RuntimeInstallRequest) {
        val metadata = installRoot.resolve("versions").resolve(".$publishedName.meta")
        Files.write(
            metadata,
            RuntimeManifestCodec.encode(request.manifest),
            StandardOpenOption.CREATE_NEW,
            StandardOpenOption.WRITE,
        )
        forceFile(metadata)
    }

    private fun ensureUnixExecutable(executable: Path) {
        if (Files.getFileAttributeView(executable, PosixFileAttributeView::class.java) == null) {
            return
        }
        if (!Files.isExecutable(executable)) {
            runCatching {
                val permissions = Files.getPosixFilePermissions(executable).toMutableSet()
                permissions += PosixFilePermission.OWNER_EXECUTE
                Files.setPosixFilePermissions(executable, permissions)
            }.getOrElse { error ->
                throw RuntimeInstallException(
                    "ENTRYPOINT_NOT_EXECUTABLE",
                    "Unable to set executable permission on the SageMath entrypoint",
                    error,
                )
            }
        }
        if (!Files.isExecutable(executable)) {
            throw RuntimeInstallException("ENTRYPOINT_NOT_EXECUTABLE", "Runtime entrypoint is not executable")
        }
    }

    private fun unzipSafely(
        archive: Path,
        payload: Path,
        cancellation: InstallationCancellation,
        control: RuntimeControl = RuntimeControl(),
    ) {
        ZipInputStream(Files.newInputStream(archive)).use { input ->
            val buffer = ByteArray(64 * 1024)
            val seen = mutableSetOf<String>()
            val directories = mutableSetOf<String>()
            var totalBytes = 0L
            var entryCount = 0
            while (true) {
                checkpoints(cancellation, control, "INSTALL")
                val entry = input.nextEntry ?: break
                entryCount++
                if (entryCount > MAX_ARCHIVE_ENTRIES) {
                    throw RuntimeInstallException("ARCHIVE_TOO_MANY_ENTRIES", "Runtime archive contains too many entries")
                }
                val rawName = entry.name.replace('\\', '/')
                val name = rawName.trimEnd('/')
                if (name.isBlank() || !RuntimeArtifact.isSafeRelativePath(name) || !seen.add(name)) {
                    throw RuntimeInstallException("ARCHIVE_UNSAFE", "Runtime archive contains an unsafe or duplicate path")
                }
                if (entry.isDirectory) {
                    directories += name
                    continue
                }
                val destination = payload.resolve(name).normalize()
                if (!destination.startsWith(payload) || Files.isSymbolicLink(destination)) {
                    throw RuntimeInstallException("ARCHIVE_UNSAFE", "Runtime archive escapes its staging directory")
                }
                val parentNames = name.split('/').dropLast(1).runningFold("") { prefix, part ->
                    if (prefix.isEmpty()) part else "$prefix/$part"
                }
                if (parentNames.any { it in seen && it !in directories }) {
                    throw RuntimeInstallException("ARCHIVE_CONFLICT", "Runtime archive contains a file/directory conflict")
                }
                Files.createDirectories(destination.parent)
                ensureDirectoryChainIsNotSymbolic(destination.parent)
                Files.newOutputStream(
                    destination,
                    StandardOpenOption.CREATE_NEW,
                    StandardOpenOption.WRITE,
                ).use { output ->
                    while (true) {
                        checkpoints(cancellation, control, "INSTALL")
                        val read = input.read(buffer)
                        if (read < 0) break
                        totalBytes += read
                        if (totalBytes > MAX_UNPACKED_BYTES) {
                            throw RuntimeInstallException("ARCHIVE_TOO_LARGE", "Runtime archive expands beyond the configured limit")
                        }
                        output.write(buffer, 0, read)
                    }
                }
            }
        }
    }

    private fun checkpoint(request: RuntimeInstallRequest, stage: String) = checkpoints(request.cancellation, request.control, stage)
    private fun controlCheckpoint(control: RuntimeControl, stage: String) {
        when {
            control.cancellation.isCancelled() -> throw RuntimeInstallException("${stage}_CANCELLED", "Runtime installation was cancelled")
            control.deadline.isExpired() -> throw RuntimeInstallException("${stage}_TIMED_OUT", "Runtime installation deadline expired")
        }
    }


    private fun checkpoints(cancellation: InstallationCancellation, control: RuntimeControl, stage: String) {
        when {
            cancellation.isCancelled() || control.cancellation.isCancelled() -> throw RuntimeInstallException("${stage}_CANCELLED", "Runtime installation was cancelled")
            control.deadline.isExpired() -> throw RuntimeInstallException("${stage}_TIMED_OUT", "Runtime installation deadline expired")
        }
    }

    private fun acquireLock(channel: FileChannel, control: RuntimeControl): FileLock {
        while (true) {
            when {
                control.cancellation.isCancelled() -> throw RuntimeInstallException("LOCK_CANCELLED", "Runtime installation was cancelled")
                control.deadline.isExpired() -> throw RuntimeInstallException("LOCK_TIMED_OUT", "Runtime installation deadline expired")
            }
            try { channel.tryLock()?.let { return it } } catch (_: OverlappingFileLockException) { }
            val remaining = control.deadline.remainingNanos()
            if (remaining != null && remaining <= 0) throw RuntimeInstallException("LOCK_TIMED_OUT", "Runtime installation deadline expired")
            Thread.sleep(if (remaining == null) 10L else minOf(10L, TimeUnit.NANOSECONDS.toMillis(remaining).coerceAtLeast(1L)))
        }
    }

    private fun moveDirectoryForPublication(source: Path, destination: Path) {
        try {
            Files.move(source, destination, StandardCopyOption.ATOMIC_MOVE)
        }
        catch (_: AtomicMoveNotSupportedException) {
            // This move targets an unpublished staging/version directory. The
            // current pointer is switched only after the destination is complete.
            Files.move(source, destination)
        }
    }

    private fun forceFile(path: Path) {
        FileChannel.open(path, StandardOpenOption.WRITE).use { it.force(true) }
    }

    private fun forceDirectory(path: Path) {
        if (PlatformDetector.detect().os == OperatingSystem.WINDOWS) {
            // Java NIO cannot reliably open a directory as a FileChannel on
            // Windows. The files and publication pointer are forced
            // separately; the atomic directory moves provide the remaining
            // publication boundary on this platform.
            return
        }
        runCatching {
            FileChannel.open(path, StandardOpenOption.READ).use { it.force(true) }
        }.getOrElse { error ->
            throw RuntimeInstallException("FSYNC_FAILED", "Unable to flush published runtime directory", error)
        }
    }

    private fun ensureDirectoryChainIsNotSymbolic(path: Path) {
        val absolute = path.toAbsolutePath().normalize()
        var current = absolute.root ?: error("Runtime install path must have a root")
        for (part in absolute) {
            current = current.resolve(part.toString())
            if (Files.exists(current, LinkOption.NOFOLLOW_LINKS) && Files.isSymbolicLink(current)) {
                throw RuntimeInstallException("SYMLINK_PATH", "Runtime install path contains a symbolic link: $current")
            }
        }
    }

    private fun sha256Bytes(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { "%02x".format(it) }

    private fun deleteRecursively(path: Path) {
        if (!Files.exists(path)) return
        Files.walk(path).use { stream ->
            stream.sorted(Comparator.reverseOrder()).forEach(Files::delete)
        }
    }

    private fun cleanupDirectory(path: Path) = deleteRecursively(path)

    companion object {
        private const val MAX_ARCHIVE_ENTRIES = 250_000
        private const val MAX_UNPACKED_BYTES = 32L * 1024 * 1024 * 1024
    }
}

private fun RuntimeArtifact.platformIsWindows(): Boolean =
    id.platform.os == OperatingSystem.WINDOWS

internal fun ensureDownloadPathIsSafe(destination: Path) {
    val absolute = destination.toAbsolutePath().normalize()
    var current = absolute.root ?: error("Download path must have a root")
    for (part in absolute) {
        current = current.resolve(part.toString())
        if (Files.isSymbolicLink(current)) {
            throw RuntimeInstallException("DOWNLOAD_DESTINATION_SYMLINK", "Download destination contains a symbolic link")
        }
    }
    if (Files.exists(absolute, LinkOption.NOFOLLOW_LINKS)) {
        throw RuntimeInstallException("DOWNLOAD_DESTINATION_EXISTS", "Download destination must not already exist")
    }
}
