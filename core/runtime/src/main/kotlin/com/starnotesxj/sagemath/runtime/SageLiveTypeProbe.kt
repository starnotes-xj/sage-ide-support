package com.starnotesxj.sagemath.runtime

import java.nio.charset.StandardCharsets
import java.util.Base64
import java.util.UUID

/**
 * A type observed from one isolated Sage process.  The concrete runtime class
 * is preserved together with its MRO so an IDE can map a runtime-only
 * ``*_with_category`` implementation to its concrete stub counterpart without
 * pretending that a public base class was the observed result.
 */
data class SageObservedType(
    val runtimeClass: String,
    val methodResolutionOrder: List<String>,
)

/** Input for a bounded, one-shot Sage source snapshot. */
data class SageLiveTypeProbeRequest(
    val target: RuntimeTarget,
    val executable: String,
    val source: String,
    val requestedNames: Set<String>,
    val fileName: String = "<sage-ide-live-snapshot>",
    val workingDirectory: String? = null,
    val control: RuntimeControl = RuntimeControl(),
    val maxOutputBytes: Int = 128 * 1024,
) {
    init {
        require(executable.isNotBlank()) { "Sage executable must not be blank" }
        require(requestedNames.all(::isSafePythonIdentifier)) {
            "Live Sage type probe accepts Python identifiers only"
        }
        require(maxOutputBytes > 0) { "Live Sage type probe output limit must be positive" }
    }

    private companion object {
        fun isSafePythonIdentifier(name: String): Boolean =
            name.matches(Regex("[A-Za-z_][A-Za-z0-9_]*"))
    }
}

data class SageLiveTypeProbeResult(
    val status: RuntimeExecutionStatus,
    val observedTypes: Map<String, SageObservedType>,
    val details: RuntimeProcessResult? = null,
    val diagnostic: String? = null,
)

/**
 * Executes an explicit source snapshot in an independent Sage process.
 *
 * Source is supplied on stdin instead of an argument or shell command, so
 * paths, quotes and Sage syntax cannot alter the launch command.  This is a
 * process isolation boundary, not a security sandbox: source can still have
 * the same external side effects it would have when the user runs it.
 */
class SageLiveTypeProbe(private val executor: RuntimeTargetExecutor) {
    fun probe(request: SageLiveTypeProbeRequest): SageLiveTypeProbeResult {
        request.control.status()?.let { return SageLiveTypeProbeResult(it, emptyMap()) }
        if (request.requestedNames.isEmpty()) {
            return SageLiveTypeProbeResult(RuntimeExecutionStatus.SUCCESS, emptyMap())
        }
        val marker = "__SAGE_IDE_LIVE_TYPE_${UUID.randomUUID()}__"
        val processResult = executor.execute(
            TargetProcessRequest(
                target = request.target,
                executable = request.executable,
                args = listOf("-c", SNAPSHOT_PROGRAM),
                workingDirectory = request.workingDirectory,
                control = request.control,
                maxOutputBytes = request.maxOutputBytes,
                standardInput = payload(request, marker),
            ),
        )
        val status = processResult.exitStatus()
        if (status != RuntimeExecutionStatus.SUCCESS) {
            return SageLiveTypeProbeResult(
                status,
                emptyMap(),
                processResult,
                processResult.standardError.trim().ifBlank { "Sage live type snapshot failed" },
            )
        }
        val observed = parse(processResult.standardOutput, marker)
        return if (observed.isEmpty()) {
            SageLiveTypeProbeResult(
                RuntimeExecutionStatus.FAILED,
                emptyMap(),
                processResult,
                "Sage live type snapshot returned no type marker",
            )
        } else {
            SageLiveTypeProbeResult(RuntimeExecutionStatus.SUCCESS, observed, processResult)
        }
    }

    private fun payload(request: SageLiveTypeProbeRequest, marker: String): ByteArray = buildString {
        append(encode(request.source)).append('\n')
        append(encode(request.fileName)).append('\n')
        append(marker).append('\n')
        append(request.requestedNames.sorted().joinToString(","))
    }.toByteArray(StandardCharsets.UTF_8)

    private fun parse(output: String, marker: String): Map<String, SageObservedType> = buildMap {
        output.lineSequence().forEach { line ->
            val parts = line.split('\t')
            if (parts.size != 4 || parts[0] != marker || !parts[1].matches(IDENTIFIER)) return@forEach
            val runtimeClass = decode(parts[2]) ?: return@forEach
            val mro = decode(parts[3])?.split(MRO_SEPARATOR)?.filter(String::isNotBlank).orEmpty()
            if (runtimeClass.isNotBlank() && mro.isNotEmpty()) {
                put(parts[1], SageObservedType(runtimeClass, mro))
            }
        }
    }

    private fun encode(value: String): String = Base64.getEncoder().encodeToString(value.toByteArray(StandardCharsets.UTF_8))

    private fun decode(value: String): String? = runCatching {
        String(Base64.getDecoder().decode(value), StandardCharsets.UTF_8)
    }.getOrNull()

    private fun RuntimeProcessResult.exitStatus(): RuntimeExecutionStatus = when {
        status != RuntimeExecutionStatus.SUCCESS -> status
        exitCode == 0 -> RuntimeExecutionStatus.SUCCESS
        else -> RuntimeExecutionStatus.FAILED
    }

    private companion object {
        val IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")
        const val MRO_SEPARATOR = "\u001f"

        /** Kept argument-free; request data always enters through stdin. */
        val SNAPSHOT_PROGRAM = """
            import base64
            import sys
            from sage.repl.preparse import preparse

            _lines = sys.stdin.buffer.read().splitlines()
            if len(_lines) != 4:
                raise RuntimeError("invalid Sage IDE live type payload")
            _source = base64.b64decode(_lines[0]).decode("utf-8")
            _filename = base64.b64decode(_lines[1]).decode("utf-8")
            _marker = _lines[2].decode("ascii")
            _names = [name for name in _lines[3].decode("ascii").split(",") if name]
            _namespace = {"__name__": "__sage_ide_live_snapshot__"}
            exec("from sage.all import *", _namespace)
            exec(compile(preparse(_source), _filename, "exec"), _namespace)
            for _name in _names:
                if _name not in _namespace:
                    continue
                _class = type(_namespace[_name])
                _runtime = "%s.%s" % (_class.__module__, _class.__qualname__)
                _mro = "\x1f".join("%s.%s" % (_base.__module__, _base.__qualname__) for _base in _class.__mro__)
                _encoded_runtime = base64.b64encode(_runtime.encode("utf-8")).decode("ascii")
                _encoded_mro = base64.b64encode(_mro.encode("utf-8")).decode("ascii")
                print(_marker + "\t" + _name + "\t" + _encoded_runtime + "\t" + _encoded_mro, flush=True)
        """.trimIndent()
    }
}
