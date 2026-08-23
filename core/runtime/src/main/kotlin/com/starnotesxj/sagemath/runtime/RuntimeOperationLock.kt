package com.starnotesxj.sagemath.runtime

import java.nio.channels.FileChannel
import java.nio.channels.OverlappingFileLockException
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardOpenOption

/**
 * Serializes mutations that publish the shared runtime current pointer.
 *
 * The installer already has a per-runtime lock for duplicate downloads. This
 * root-level lock covers the shared current/history files and also coordinates
 * lifecycle operations across separate IDE processes.
 */
internal fun <T> withRuntimeOperationLock(
    root: Path,
    checkpoint: (() -> Unit)? = null,
    action: () -> T,
): T {
    val normalizedRoot = root.toAbsolutePath().normalize()
    ensureOperationPathIsNotSymbolic(normalizedRoot)
    Files.createDirectories(normalizedRoot)
    ensureOperationPathIsNotSymbolic(normalizedRoot)

    val lockPath = normalizedRoot.resolve(".runtime-operations.lock")
    if (Files.isSymbolicLink(lockPath)) {
        throw RuntimeInstallException("LOCK_PATH_INVALID", "Runtime operation lock path is symbolic")
    }
    FileChannel.open(lockPath, StandardOpenOption.CREATE, StandardOpenOption.WRITE).use { channel ->
        while (true) {
            checkpoint?.invoke()
            val lock = try {
                channel.tryLock()
            }
            catch (_: OverlappingFileLockException) {
                null
            }
            if (lock != null) {
                return lock.use { action() }
            }
            try {
                Thread.sleep(10L)
            }
            catch (error: InterruptedException) {
                Thread.currentThread().interrupt()
                throw RuntimeInstallException("LOCK_INTERRUPTED", "Runtime operation lock acquisition was interrupted", error)
            }
        }
    }
}
private fun ensureOperationPathIsNotSymbolic(path: Path) {
    var current = path.root ?: error("Runtime operation path must have a root")
    for (part in path) {
        current = current.resolve(part.toString())
        if (Files.isSymbolicLink(current)) {
            throw RuntimeInstallException("SYMLINK_PATH", "Runtime operation path contains a symbolic link: $current")
        }
    }
}
