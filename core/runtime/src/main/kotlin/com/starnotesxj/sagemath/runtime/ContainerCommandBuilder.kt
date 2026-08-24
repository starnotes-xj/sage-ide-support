package com.starnotesxj.sagemath.runtime

import java.nio.file.Path

/** Supported command-line container engines; no implicit Docker/Podman fallback is performed. */
enum class ContainerEngine(val executable: String) {
    DOCKER("docker"),
    PODMAN("podman"),
}

data class ContainerRunSpec(
    val engine: ContainerEngine,
    val image: String,
    val containerCommand: String,
    val hostScriptDirectory: Path,
    val containerWorkingDirectory: String,
    val scriptFileName: String,
    val sageArguments: List<String> = emptyList(),
    val scriptArguments: List<String> = emptyList(),
) {
    init {
        require(image.isNotBlank() && image.none(Char::isISOControl)) { "Container image must be printable and non-blank" }
        require(containerCommand.isNotBlank() && containerCommand.none(Char::isISOControl)) { "Container Sage command must be printable and non-blank" }
        require(scriptFileName.isNotBlank() && scriptFileName != "." && scriptFileName != ".." && !scriptFileName.contains('/') && !scriptFileName.contains('\\')) {
            "Container script file name must be a plain file name"
        }
        require(!hostScriptDirectory.toString().contains('\u0000')) { "Container host directory must be printable" }
        require(containerWorkingDirectory.startsWith('/') && !containerWorkingDirectory.startsWith("//")) {
            "Container working directory must be an absolute POSIX path"
        }
        val components = containerWorkingDirectory.split('/').drop(1)
        require(components.none { it.isBlank() || it == "." || it == ".." }) {
            "Container working directory contains traversal or empty components"
        }
    }
}

/** Builds argv only; paths and user arguments never pass through a shell. */
object ContainerCommandBuilder {
    fun build(spec: ContainerRunSpec): List<String> = listOf(
        spec.engine.executable,
        "run",
        "--rm",
        "--mount",
        "type=bind,src=${spec.hostScriptDirectory.toAbsolutePath().normalize()},dst=${spec.containerWorkingDirectory}",
        "--workdir",
        spec.containerWorkingDirectory,
        spec.image,
        spec.containerCommand,
    ) + spec.sageArguments + listOf(spec.scriptFileName) + spec.scriptArguments
}

/** Validates a Settings container profile before it can be used as a run target. */
object ContainerProfileValidator {
    fun validate(engine: String, image: String, command: String, workingDirectory: String): RuntimeOperationResult<ContainerEngine> {
        val selected = ContainerEngine.entries.firstOrNull { it.executable == engine.trim() }
            ?: return failure("Container engine must be exactly docker or podman")
        return runCatching {
            ContainerRunSpec(selected, image, command, Path.of("."), workingDirectory, "placeholder.sage")
            RuntimeOperationResult(selected)
        }.getOrElse { failure(it.message ?: "Container profile is invalid") }
    }

    private fun failure(message: String): RuntimeOperationResult<ContainerEngine> = RuntimeOperationResult(
        null,
        listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "CONTAINER_PROFILE", message)),
        false,
    )
}

/** Executes image-owned probe argv through the local container CLI. */
fun interface ContainerRuntimeExecutor {
    fun execute(
        engine: ContainerEngine,
        image: String,
        command: List<String>,
        control: RuntimeControl,
        maxOutputBytes: Int,
    ): RuntimeProcessResult
}

/** Production adapter: the image owns Sage; no host runtime path is mounted into probes. */
class JdkContainerRuntimeExecutor(
    private val executor: RuntimeProcessExecutor = JdkRuntimeProcessExecutor(),
) : ContainerRuntimeExecutor {
    override fun execute(
        engine: ContainerEngine,
        image: String,
        command: List<String>,
        control: RuntimeControl,
        maxOutputBytes: Int,
    ): RuntimeProcessResult = executor.execute(
        RuntimeProcessRequest(
            command = listOf(engine.executable, "run", "--rm", image) + command,
            control = control,
            maxOutputBytes = maxOutputBytes,
        ),
    )
}

/** Probe an image-owned Sage executable without mapping a host managed runtime into it. */
class ContainerRuntimeProbe(private val executor: ContainerRuntimeExecutor) {
    fun probe(
        engine: ContainerEngine,
        image: String,
        command: String = "sage",
        control: RuntimeControl = RuntimeControl(),
        maxOutputBytes: Int = 64 * 1024,
    ): TargetRuntimeProbeResult {
        require(maxOutputBytes > 0) { "Container probe output limit must be positive" }
        control.status()?.let { status ->
            return TargetRuntimeProbeResult(status, null, null)
        }
        if (image.isBlank() || image.any(Char::isISOControl) || command.isBlank() || command.any(Char::isISOControl)) {
            return failedProbe(
                RuntimeExecutionStatus.FAILED,
                "CONTAINER_PROBE",
                "Container image and Sage command must be printable and non-blank",
            )
        }
        val version = executor.execute(engine, image, listOf(command, "--version"), control, maxOutputBytes)
        if (version.status != RuntimeExecutionStatus.SUCCESS || version.exitCode != 0 || version.outputTruncated || version.standardOutput.trim().isBlank()) {
            return TargetRuntimeProbeResult(
                status = version.exitStatus(),
                version = version.standardOutput.trim().ifBlank { null },
                expressionOutput = null,
                details = version,
                diagnostics = listOf(
                    RuntimeDiagnostic(
                        RuntimeDiagnosticCode.TARGET_PROBE_FAILED,
                        "CONTAINER_PROBE_VERSION",
                        "Container Sage version probe failed",
                        details = probeDetails(version),
                    ),
                ),
            )
        }
        control.status()?.let { status ->
            return TargetRuntimeProbeResult(status, version.standardOutput.trim(), null, version)
        }
        val expression = executor.execute(engine, image, listOf(command, "-c", "print(2+2)"), control, maxOutputBytes)
        val expressionOutput = expression.standardOutput.trim().ifBlank { null }
        val status = expression.exitStatus()
        return TargetRuntimeProbeResult(
            status = if (status == RuntimeExecutionStatus.SUCCESS && !expression.outputTruncated && expressionOutput == "4") {
                RuntimeExecutionStatus.SUCCESS
            } else if (status == RuntimeExecutionStatus.SUCCESS) {
                RuntimeExecutionStatus.FAILED
            } else {
                status
            },
            version = version.standardOutput.trim(),
            expressionOutput = expressionOutput,
            details = expression,
            diagnostics = if (status == RuntimeExecutionStatus.SUCCESS && !expression.outputTruncated && expressionOutput == "4") {
                emptyList()
            } else {
                listOf(
                    RuntimeDiagnostic(
                        RuntimeDiagnosticCode.TARGET_PROBE_FAILED,
                        "CONTAINER_PROBE_EXPRESSION",
                        "Container Sage expression probe did not produce exactly 4",
                        details = probeDetails(expression) + mapOf("expected" to "4", "actual" to (expressionOutput ?: "")),
                    ),
                )
            },
        )
    }

    private fun failedProbe(status: RuntimeExecutionStatus, stage: String, message: String) = TargetRuntimeProbeResult(
        status = status,
        version = null,
        expressionOutput = null,
        diagnostics = listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, stage, message)),
    )

    private fun probeDetails(result: RuntimeProcessResult): Map<String, String> = buildMap {
        result.exitCode?.let { put("exitCode", it.toString()) }
        result.standardError.trim().take(512).takeIf { it.isNotEmpty() }?.let { put("stderr", it) }
        put("outputTruncated", result.outputTruncated.toString())
    }

    private fun RuntimeProcessResult.exitStatus(): RuntimeExecutionStatus = if (status != RuntimeExecutionStatus.SUCCESS) {
        status
    } else if (exitCode == 0) {
        RuntimeExecutionStatus.SUCCESS
    } else {
        RuntimeExecutionStatus.FAILED
    }
}

internal fun containerTarget(engine: ContainerEngine, image: String): RuntimeTarget.Docker = RuntimeTarget.Docker(image = image, engine = engine)
