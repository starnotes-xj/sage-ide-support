package com.starnotesxj.sageide.type

import com.intellij.execution.process.ProcessAdapter
import com.intellij.execution.process.ProcessEvent
import com.intellij.execution.process.ProcessHandler
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.starnotesxj.sagemath.runtime.SageRunTypeFeedbackProtocol
import java.io.File
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/**
 * One opt-in feedback channel attached to a normal Sage file run.
 *
 * It loads a fixed ``sitecustomize`` hook for that child process only. The
 * hook delegates to Sage's original file runner, then writes a bounded private
 * sidecar.  No user source is rewritten, no second Sage process is started and
 * no marker is emitted into the Run console.
 */
internal class SageRunTypeFeedbackSession private constructor(
    private val scriptFile: VirtualFile,
    private val sourceDigest: String,
    private val runtimeKey: String,
    private val bootstrapDirectory: Path,
    private val responseFile: Path,
    private val runId: String,
) : AutoCloseable {
    private val closed = AtomicBoolean(false)

    fun nativeEnvironment(): Map<String, String> = commonEnvironment() + mapOf(
        "PYTHONPATH" to listOf(bootstrapDirectory.toString(), System.getenv("PYTHONPATH"))
            .filterNotNull()
            .filter(String::isNotBlank)
            .joinToString(File.pathSeparator),
    )

    /**
     * WSL receives dedicated variables through WSLENV; the fixed shell prefix
     * prepends the bootstrap to its existing Linux PYTHONPATH instead of
     * replacing user configuration.
     */
    fun wslEnvironment(): Map<String, String> {
        val common = commonEnvironment() + mapOf(SageRunTypeFeedbackProtocol.BOOTSTRAP_PATH_ENV to bootstrapDirectory.toString())
        val encodedNames = setOf(
            SageRunTypeFeedbackProtocol.BOOTSTRAP_PATH_ENV,
            SageRunTypeFeedbackProtocol.OUTPUT_PATH_ENV,
            SageRunTypeFeedbackProtocol.RUN_ID_ENV,
            SageRunTypeFeedbackProtocol.SOURCE_DIGEST_ENV,
        )
        val inherited = System.getenv("WSLENV").orEmpty()
            .split(':')
            .filter(String::isNotBlank)
            .filterNot { it.substringBefore('/').uppercase() in encodedNames }
        val additions = listOf(
            "${SageRunTypeFeedbackProtocol.BOOTSTRAP_PATH_ENV}/p",
            "${SageRunTypeFeedbackProtocol.OUTPUT_PATH_ENV}/p",
            "${SageRunTypeFeedbackProtocol.RUN_ID_ENV}/u",
            "${SageRunTypeFeedbackProtocol.SOURCE_DIGEST_ENV}/u",
        )
        return common + ("WSLENV" to (inherited + additions).joinToString(":"))
    }

    fun attach(handler: ProcessHandler, project: Project) {
        handler.addProcessListener(object : ProcessAdapter() {
            override fun processTerminated(event: ProcessEvent) {
                ApplicationManager.getApplication().executeOnPooledThread {
                    try {
                        val feedback = readFeedback()
                        if (feedback != null && !project.isDisposed && scriptFile.isValid) {
                            SageLiveTypeSnapshotService.getInstance(project).recordRunEvidence(
                                scriptFile,
                                sourceDigest,
                                runtimeKey,
                                feedback.observedTypes,
                            )
                        }
                    } finally {
                        close()
                    }
                }
            }
        })
    }

    private fun commonEnvironment(): Map<String, String> = mapOf(
        SageRunTypeFeedbackProtocol.OUTPUT_PATH_ENV to responseFile.toString(),
        SageRunTypeFeedbackProtocol.RUN_ID_ENV to runId,
        SageRunTypeFeedbackProtocol.SOURCE_DIGEST_ENV to sourceDigest,
    )

    private fun readFeedback() = runCatching {
        if (!Files.isRegularFile(responseFile) || Files.size(responseFile) > SageRunTypeFeedbackProtocol.MAX_SIDECAR_BYTES) {
            return@runCatching null
        }
        SageRunTypeFeedbackProtocol.decode(
            Files.readString(responseFile, StandardCharsets.UTF_8),
            runId,
            sourceDigest,
        )
    }.getOrNull()

    override fun close() {
        if (!closed.compareAndSet(false, true)) return
        runCatching { Files.deleteIfExists(responseFile) }
        runCatching { Files.deleteIfExists(bootstrapDirectory.resolve("sitecustomize.py")) }
        runCatching { Files.deleteIfExists(bootstrapDirectory) }
    }

    companion object {
        /** Constant shell body: user paths and arguments are always separate argv values. */
        val WSL_BOOTSTRAP_COMMAND = """
            PYTHONPATH="${'$'}{${SageRunTypeFeedbackProtocol.BOOTSTRAP_PATH_ENV}}${'$'}{PYTHONPATH:+:${'$'}PYTHONPATH}"
            export PYTHONPATH
            exec "${'$'}@"
        """.trimIndent()

        fun prepare(scriptPath: String, runtimeKey: String): SageRunTypeFeedbackSession? = runCatching {
            val path = Path.of(scriptPath).toAbsolutePath().normalize()
            if (!Files.isRegularFile(path)) return@runCatching null
            val virtualFile = LocalFileSystem.getInstance().findFileByNioFile(path) ?: return@runCatching null
            val digest = sha256(Files.readAllBytes(path))
            val directory = Files.createTempDirectory("sage-ide-run-feedback-")
            val response = directory.resolve("feedback.tsv")
            Files.writeString(directory.resolve("sitecustomize.py"), SageRunTypeFeedbackProtocol.SITE_CUSTOMIZE_SOURCE, StandardCharsets.UTF_8)
            SageRunTypeFeedbackSession(virtualFile, digest, runtimeKey, directory, response, UUID.randomUUID().toString())
        }.getOrNull()

        private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
            .digest(bytes)
            .joinToString("") { byte -> "%02x".format(byte) }
    }
}
