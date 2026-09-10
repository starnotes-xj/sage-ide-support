package com.starnotesxj.sagemath.runtime

import java.nio.charset.StandardCharsets
import java.util.Base64
import java.util.UUID
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/** A query sent to a persistent Sage live-type worker. */
data class SageLiveTypeWorkerQuery(
    val source: String,
    val requestedNames: Set<String>,
    val fileName: String = "<sage-ide-live-snapshot>",
    val control: RuntimeControl = RuntimeControl(),
) {
    init {
        require(requestedNames.all { it.matches(SAFE_IDENTIFIER) }) {
            "Live Sage type worker accepts Python identifiers only"
        }
    }

    private companion object {
        val SAFE_IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")
    }
}

/**
 * Long-lived Sage interpreter used by the IDE's optional live type service.
 * Every query receives a fresh user namespace cloned from Sage's imported
 * globals, while the expensive Sage import remains resident in the process.
 *
 * This is intentionally a process boundary, not a security sandbox: source
 * can still perform the same external side effects as a normal Sage run.
 */
class SageLiveTypeWorker(
    private val target: RuntimeTarget,
    private val executable: String,
    private val maxOutputBytes: Int = 128 * 1024,
) : AutoCloseable {
    init {
        require(executable.isNotBlank()) { "Sage executable must not be blank" }
        require(maxOutputBytes > 0) { "Sage live type worker output limit must be positive" }
    }

    private val lock = Any()
    private val responses = LinkedBlockingQueue<String>()
    private val stdoutOverflow = AtomicBoolean(false)
    private var process: Process? = null
    private var stderrTail: BoundedText? = null

    fun probe(query: SageLiveTypeWorkerQuery): SageLiveTypeProbeResult = synchronized(lock) {
        if (query.requestedNames.isEmpty()) {
            return SageLiveTypeProbeResult(RuntimeExecutionStatus.SUCCESS, emptyMap())
        }
        query.control.status()?.let { return SageLiveTypeProbeResult(it, emptyMap()) }
        val current = runCatching { ensureStarted() }.getOrElse { error ->
            return SageLiveTypeProbeResult(RuntimeExecutionStatus.FAILED, emptyMap(), diagnostic = error.message)
        }
        val requestId = UUID.randomUUID().toString()
        val line = SageLiveTypeWorkerProtocol.requestLine(requestId, query)
        try {
            current.outputStream.write(line.toByteArray(StandardCharsets.UTF_8))
            current.outputStream.flush()
        } catch (error: Throwable) {
            closeLocked()
            return SageLiveTypeProbeResult(RuntimeExecutionStatus.FAILED, emptyMap(), diagnostic = error.message)
        }

        while (true) {
            query.control.status()?.let {
                closeLocked()
                return SageLiveTypeProbeResult(it, emptyMap())
            }
            val response = responses.poll(WORKER_POLL_MILLIS, TimeUnit.MILLISECONDS)
            if (response != null) {
                val decoded = SageLiveTypeWorkerProtocol.decodeResponse(response, requestId)
                if (decoded != null) {
                    if (decoded.status != RuntimeExecutionStatus.SUCCESS) {
                        return SageLiveTypeProbeResult(
                            decoded.status,
                            emptyMap(),
                            diagnostic = decoded.diagnostic ?: stderrTail?.text(),
                        )
                    }
                    if (decoded.observedTypes.isNotEmpty()) {
                        return SageLiveTypeProbeResult(RuntimeExecutionStatus.SUCCESS, decoded.observedTypes)
                    }
                    return SageLiveTypeProbeResult(
                        RuntimeExecutionStatus.FAILED,
                        emptyMap(),
                        diagnostic = "Sage live type worker returned no requested type",
                    )
                }
            }
            if (stdoutOverflow.get()) {
                closeLocked()
                return SageLiveTypeProbeResult(
                    RuntimeExecutionStatus.FAILED,
                    emptyMap(),
                    diagnostic = "Sage live type worker response exceeded the output limit",
                )
            }
            if (!current.isAlive) {
                val diagnostic = stderrTail?.text()?.ifBlank { null } ?: "Sage live type worker exited"
                closeLocked()
                return SageLiveTypeProbeResult(RuntimeExecutionStatus.FAILED, emptyMap(), diagnostic = diagnostic)
            }
        }
        error("Sage live type worker query loop terminated unexpectedly")
    }

    private fun ensureStarted(): Process {
        process?.takeIf(Process::isAlive)?.let { return it }
        check(target !is RuntimeTarget.RemoteSsh) { "Live Sage type worker does not support SSH targets" }
        require(executable.isNotBlank()) { "Sage executable must not be blank" }
        val started = ProcessBuilder(
            RuntimeTargetCommandBuilder.build(
                TargetProcessRequest(target, executable, listOf("-c", SageLiveTypeWorkerProtocol.PROGRAM)),
            ),
        ).start()
        responses.clear()
        stdoutOverflow.set(false)
        val stderr = BoundedText(maxOutputBytes)
        stderrTail = stderr
        thread(isDaemon = true, name = "sage-live-worker-stdout") {
            started.inputStream.bufferedReader(StandardCharsets.UTF_8).useLines { lines ->
                lines.forEach { line ->
                    if (line.toByteArray(StandardCharsets.UTF_8).size > maxOutputBytes) {
                        stdoutOverflow.set(true)
                    } else {
                        responses.offer(line)
                    }
                }
            }
        }
        thread(isDaemon = true, name = "sage-live-worker-stderr") {
            started.errorStream.bufferedReader(StandardCharsets.UTF_8).use { reader ->
                val buffer = CharArray(4096)
                while (true) {
                    val count = reader.read(buffer)
                    if (count < 0) break
                    stderr.append(String(buffer, 0, count))
                }
            }
        }
        process = started
        return started
    }

    override fun close() = synchronized(lock) { closeLocked() }

    private fun closeLocked() {
        process?.let { current ->
            runCatching { current.outputStream.close() }
            runCatching { current.destroy() }
            if (!current.waitFor(100, TimeUnit.MILLISECONDS) && current.isAlive) {
                runCatching { current.destroyForcibly() }
            }
        }
        process = null
        responses.clear()
        stdoutOverflow.set(false)
    }

    private class BoundedText(private val limit: Int) {
        private val value = StringBuilder()
        @Synchronized
        fun append(text: String) {
            if (value.length >= limit) return
            value.append(text.take(limit - value.length))
        }

        @Synchronized
        fun text(): String = value.toString()
    }

    companion object {
        private const val WORKER_POLL_MILLIS = 20L
    }
}

/** Framing and parsing for the worker's ASCII/base64 line protocol. */
internal object SageLiveTypeWorkerProtocol {
    const val MAGIC = "__SAGE_IDE_LIVE_WORKER__"
    private const val RECORD_SEPARATOR = "\u001e"
    private const val MRO_SEPARATOR = "\u001f"
    private val IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")

    fun requestLine(id: String, query: SageLiveTypeWorkerQuery): String = buildString {
        append(id).append('\t')
        append(encode(query.source)).append('\t')
        append(encode(query.fileName)).append('\t')
        append(query.requestedNames.sorted().joinToString(","))
        append('\n')
    }

    fun decodeResponse(line: String, expectedId: String): WorkerResponse? {
        val parts = line.trimEnd('\r', '\n').split('\t', limit = 4)
        if (parts.size != 4 || parts[0] != MAGIC || parts[1] != expectedId) return null
        val payload = decode(parts[3]) ?: return null
        if (parts[2] != "OK") return WorkerResponse(RuntimeExecutionStatus.FAILED, emptyMap(), payload)
        val values = buildMap {
            payload.split(RECORD_SEPARATOR).forEach { record ->
                val fields = record.split('|', limit = 3)
                if (fields.size != 3 || !fields[0].matches(IDENTIFIER)) return@forEach
                val runtime = decode(fields[1]) ?: return@forEach
                val mro = decode(fields[2])?.split(MRO_SEPARATOR)?.filter(String::isNotBlank).orEmpty()
                if (runtime.isNotBlank() && mro.isNotEmpty()) put(fields[0], SageObservedType(runtime, mro))
            }
        }
        return WorkerResponse(RuntimeExecutionStatus.SUCCESS, values, null)
    }

    private fun encode(value: String): String = Base64.getEncoder().encodeToString(value.toByteArray(StandardCharsets.UTF_8))
    private fun decode(value: String): String? = runCatching {
        String(Base64.getDecoder().decode(value), StandardCharsets.UTF_8)
    }.getOrNull()

    data class WorkerResponse(
        val status: RuntimeExecutionStatus,
        val observedTypes: Map<String, SageObservedType>,
        val diagnostic: String?,
    )

    /** Fixed program; user source and names always arrive as request data. */
    val PROGRAM = """
        import base64
        import contextlib
        import io
        import sys
        import traceback
        from sage.repl.preparse import preparse
        _MAGIC = '$MAGIC'
        _BASE = {'__name__': '__sage_ide_live_snapshot__'}
        exec('from sage.all import *', _BASE)
        def _send(_id, _status, _payload):
            _encoded = base64.b64encode(_payload.encode('utf-8')).decode('ascii')
            sys.__stdout__.write(_MAGIC + '\t' + _id + '\t' + _status + '\t' + _encoded + '\n')
            sys.__stdout__.flush()
        def _describe(_value):
            _class = type(_value)
            _runtime = '%s.%s' % (_class.__module__, _class.__qualname__)
            _mro = '\x1f'.join('%s.%s' % (_base.__module__, _base.__qualname__) for _base in _class.__mro__)
            return base64.b64encode(_runtime.encode()).decode('ascii') + '|' + base64.b64encode(_mro.encode()).decode('ascii')
        while True:
            _raw = sys.stdin.buffer.readline()
            if not _raw:
                break
            _request_id = 'invalid'
            try:
                _request_id, _source64, _filename64, _names = _raw.rstrip(b'\r\n').decode('ascii').split('\t', 3)
                _source = base64.b64decode(_source64).decode('utf-8')
                _filename = base64.b64decode(_filename64).decode('utf-8')
                _namespace = dict(_BASE)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    exec(compile(preparse(_source), _filename, 'exec'), _namespace)
                _records = []
                for _name in _names.split(','):
                    if _name and _name in _namespace:
                        _records.append(_name + '|' + _describe(_namespace[_name]))
                _send(_request_id, 'OK', '\x1e'.join(_records))
            except Exception:
                _send(_request_id, 'ERR', traceback.format_exc(limit=8))
    """.trimIndent()
}
