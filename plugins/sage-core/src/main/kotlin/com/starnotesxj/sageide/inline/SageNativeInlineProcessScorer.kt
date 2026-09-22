package com.starnotesxj.sageide.inline

import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.util.SystemInfoRt
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.BufferedWriter
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.security.MessageDigest
import java.util.concurrent.locks.ReentrantLock
import kotlin.concurrent.withLock

/**
 * One persistent, single-flight local scorer process.
 *
 * [warmUp] is the only method allowed to spawn the executable. Completion
 * requests only use an already-ready process, and abandon it on a transport
 * failure so the semantic backend remains immediate and safe.
 */
internal class SageNativeInlineProcessScorer(
    private val executable: Path,
) : SageInlineNativeScorer, AutoCloseable {
    private val lock = ReentrantLock()
    private var process: Process? = null
    private var input: BufferedWriter? = null
    private var output: BufferedReader? = null

    fun warmUp(): Boolean = lock.withLock {
        if (process?.isAlive == true) return true
        closeLocked()
        return runCatching {
            val started = ProcessBuilder(executable.toString())
                .redirectError(ProcessBuilder.Redirect.DISCARD)
                .start()
            process = started
            input = started.outputStream.bufferedWriter()
            output = started.inputStream.bufferedReader()
            true
        }.getOrElse { error ->
            LOG.debug("Unable to start native Sage inline scorer", error)
            closeLocked()
            false
        }
    }

    override suspend fun chooseCandidate(request: SageInlineScoringRequest): String? = withContext(Dispatchers.IO) {
        lock.withLock {
            val activeProcess = process?.takeIf(Process::isAlive) ?: return@withLock null
            val activeInput = input ?: return@withLock null
            val activeOutput = output ?: return@withLock null
            runCatching {
                activeInput.write(SageInlineNativeProtocol.encodeRequest(request))
                activeInput.newLine()
                activeInput.flush()
                while (!activeOutput.ready()) {
                    check(activeProcess.isAlive) { "Native Sage inline scorer exited" }
                    Thread.sleep(RESPONSE_POLL_MILLIS)
                }
                SageInlineNativeProtocol.decodeResponse(activeOutput.readLine() ?: "")
            }.getOrElse { error ->
                LOG.debug("Native Sage inline scorer request failed", error)
                closeLocked()
                null
            }
        }
    }

    override fun close() = lock.withLock(::closeLocked)

    private fun closeLocked() {
        input?.runCatching(BufferedWriter::close)
        output?.runCatching(BufferedReader::close)
        process?.destroyForcibly()
        input = null
        output = null
        process = null
    }

    private companion object {
        private const val RESPONSE_POLL_MILLIS = 1L
        private val LOG = Logger.getInstance(SageNativeInlineProcessScorer::class.java)
    }
}

/** Extracts only the binary bundled for the running IDE platform. */
internal object SageNativeInlineExecutable {
    private const val WINDOWS_RESOURCE = "native/win-x64/sage-inline-native.exe"
    private const val LINUX_RESOURCE = "native/linux-x64/sage-inline-native"

    fun extractTo(cacheDirectory: Path): Path? {
        if (!isSupportedArchitecture()) return null
        val resource = when {
            SystemInfoRt.isWindows -> WINDOWS_RESOURCE
            SystemInfoRt.isLinux -> LINUX_RESOURCE
            else -> return null
        }
        val stream = SageNativeInlineExecutable::class.java.classLoader.getResourceAsStream(resource) ?: return null
        return stream.use { source ->
            val contents = source.readBytes()
            val fingerprint = MessageDigest.getInstance("SHA-256")
                .digest(contents)
                .joinToString("") { byte -> "%02x".format(byte.toInt() and 0xff) }
            val target = cacheDirectory.resolve(fingerprint).resolve(resource.substringAfterLast('/'))
            Files.createDirectories(target.parent)
            if (!Files.isRegularFile(target) || !Files.readAllBytes(target).contentEquals(contents)) {
                contents.inputStream().use { input ->
                    Files.copy(input, target, StandardCopyOption.REPLACE_EXISTING)
                }
                target.toFile().setExecutable(true, true)
            }
            target
        }
    }

    private fun isSupportedArchitecture(): Boolean =
        System.getProperty("os.arch").lowercase() in setOf("amd64", "x86_64")
}
