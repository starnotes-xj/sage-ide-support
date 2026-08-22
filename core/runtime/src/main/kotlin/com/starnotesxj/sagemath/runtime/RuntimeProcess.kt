package com.starnotesxj.sagemath.runtime

import java.nio.charset.StandardCharsets
import java.nio.file.Path
import java.time.Duration
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

data class RuntimeProcessRequest(
    val command: List<String>, val workingDirectory: Path? = null,
    val environment: Map<String, String> = emptyMap(),
    val control: RuntimeControl = RuntimeControl(), val maxOutputBytes: Int = 1024 * 1024,
) { init { require(command.isNotEmpty() && command.all(String::isNotEmpty)); require(maxOutputBytes > 0) } }
data class RuntimeProcessResult(val status: RuntimeExecutionStatus, val exitCode: Int?, val standardOutput: String, val standardError: String, val durationMillis: Long, val outputTruncated: Boolean, val failure: Throwable? = null)
fun interface RuntimeProcessExecutor { fun execute(request: RuntimeProcessRequest): RuntimeProcessResult }

/** JDK ProcessBuilder adapter: no shell, bounded output, deadline/cancellation kills. */
class JdkRuntimeProcessExecutor(private val pollInterval: Duration = Duration.ofMillis(10)) : RuntimeProcessExecutor {
    override fun execute(request: RuntimeProcessRequest): RuntimeProcessResult {
        val started = System.nanoTime()
        request.control.status()?.let { return result(it, null, "", "", started, false) }
        val process = try { ProcessBuilder(request.command).apply { request.workingDirectory?.let { directory(it.toFile()) }; environment().putAll(request.environment) }.start() }
        catch (error: Throwable) { return result(RuntimeExecutionStatus.FAILED, null, "", "", started, false, error) }
        val out = BoundedOutput(request.maxOutputBytes); val err = BoundedOutput(request.maxOutputBytes)
        val outThread = thread(isDaemon = true, name = "sage-runtime-stdout") { process.inputStream.use { out.read(it) } }
        val errThread = thread(isDaemon = true, name = "sage-runtime-stderr") { process.errorStream.use { err.read(it) } }
        var status = RuntimeExecutionStatus.SUCCESS
        while (true) {
            request.control.status()?.let { status = it; process.destroy(); if (!process.waitFor(100, TimeUnit.MILLISECONDS) && process.isAlive) process.destroyForcibly(); break }
            if (process.waitFor(pollInterval.toNanos().coerceAtLeast(1), TimeUnit.NANOSECONDS)) break
        }
        if (process.isAlive) process.destroyForcibly()
        outThread.join(1000); errThread.join(1000)
        return result(status, if (status == RuntimeExecutionStatus.SUCCESS) process.exitValue() else null, out.text(), err.text(), started, out.truncated || err.truncated)
    }
    private fun result(s: RuntimeExecutionStatus, e: Int?, o: String, x: String, started: Long, t: Boolean, f: Throwable? = null) = RuntimeProcessResult(s, e, o, x, (System.nanoTime()-started)/1_000_000, t, f)
    private class BoundedOutput(private val limit: Int) { private val bytes = java.io.ByteArrayOutputStream(limit); var truncated=false; private set
        fun read(input: java.io.InputStream) { val b=ByteArray(8192); while(true) { val n=input.read(b); if(n<0)return; val a=(limit-bytes.size()).coerceAtLeast(0).coerceAtMost(n); if(a>0)bytes.write(b,0,a); if(a<n)truncated=true } }
        fun text()=bytes.toString(StandardCharsets.UTF_8)
    }
}
