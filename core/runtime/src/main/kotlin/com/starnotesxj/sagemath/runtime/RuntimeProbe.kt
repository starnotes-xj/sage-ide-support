package com.starnotesxj.sagemath.runtime

import java.nio.file.Path

data class RuntimeProbeRequest(val executable: Path, val workingDirectory: Path? = executable.parent, val control: RuntimeControl = RuntimeControl(), val maxOutputBytes: Int = 64 * 1024)
data class RuntimeProbeResult(val status: RuntimeExecutionStatus, val version: String?, val expressionOutput: String?, val details: RuntimeProcessResult?)

/** Checks Sage version and evaluates a minimal Sage/Python expression. */
class RuntimeProbe(private val executor: RuntimeProcessExecutor) {
    fun probe(request: RuntimeProbeRequest): RuntimeProbeResult {
        request.control.status()?.let { return RuntimeProbeResult(it, null, null, null) }
        val version = executor.execute(RuntimeProcessRequest(listOf(request.executable.toString(), "--version"), request.workingDirectory, control=request.control, maxOutputBytes=request.maxOutputBytes))
        if (version.status != RuntimeExecutionStatus.SUCCESS || version.exitCode != 0) return RuntimeProbeResult(version.exitStatus(), version.standardOutput.trim().ifBlank { null }, null, version)
        val expression = executor.execute(RuntimeProcessRequest(listOf(request.executable.toString(), "-c", "print(2+2)"), request.workingDirectory, control=request.control, maxOutputBytes=request.maxOutputBytes))
        return RuntimeProbeResult(expression.exitStatus(), version.standardOutput.trim().ifBlank { null }, expression.standardOutput.trim().ifBlank { null }, expression)
    }
    private fun RuntimeProcessResult.exitStatus() = if (status != RuntimeExecutionStatus.SUCCESS) status else if (exitCode == 0) RuntimeExecutionStatus.SUCCESS else RuntimeExecutionStatus.FAILED
}
