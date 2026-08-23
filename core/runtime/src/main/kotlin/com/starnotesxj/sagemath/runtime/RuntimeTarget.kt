package com.starnotesxj.sagemath.runtime

import java.nio.file.Path
import java.nio.file.Paths

sealed interface RuntimeTarget {
    /** The target platform, when the transport can state it explicitly. */
    val targetPlatform: PlatformTriple?

    data object Native : RuntimeTarget {
        override val targetPlatform: PlatformTriple? = null
    }

    data class Wsl(
        val distribution: String,
        val pathMapping: RuntimePathMapping? = null,
        override val targetPlatform: PlatformTriple = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.UNKNOWN),
    ) : RuntimeTarget {
        init { require(distribution.isNotBlank()) { "WSL distribution must not be blank" } }
    }

    data class Docker(
        val image: String,
        val pathMapping: RuntimePathMapping? = null,
        override val targetPlatform: PlatformTriple = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.UNKNOWN),
    ) : RuntimeTarget {
        init { require(image.isNotBlank()) { "Docker image must not be blank" } }
    }

    data class RemoteSsh(
        val host: String,
        val user: String? = null,
        val port: Int = 22,
        val pathMapping: RuntimePathMapping? = null,
        override val targetPlatform: PlatformTriple? = null,
    ) : RuntimeTarget {
        init {
            require(host.isNotBlank()) { "Remote host must not be blank" }
            require(port in 1..65535) { "Remote SSH port must be valid" }
        }
    }
}

/**
 * Compatibility is intentionally limited to facts known by the target descriptor.
 * Native and SSH targets may be heterogeneous, so they require a probe rather
 * than guessing from the local JVM or host name.
 */
object RuntimeTargetCompatibility {
    fun diagnostic(runtimeId: SageRuntimeId, target: RuntimeTarget): RuntimeDiagnostic? {
        val targetPlatform = target.targetPlatform ?: return null
        val runtimePlatform = runtimeId.platform
        if (targetPlatform.os != OperatingSystem.UNKNOWN &&
            runtimePlatform.os != OperatingSystem.UNKNOWN &&
            targetPlatform.os != runtimePlatform.os
        ) {
            return RuntimeDiagnostic(
                RuntimeDiagnosticCode.TARGET_MISMATCH,
                "SDK_TARGET_VALIDATE",
                "Selected SageMath runtime platform does not match the target operating system",
                details = mapOf("runtimePlatform" to runtimePlatform.toString(), "targetPlatform" to targetPlatform.toString()),
            )
        }
        if (targetPlatform.architecture != CpuArchitecture.UNKNOWN &&
            runtimePlatform.architecture != CpuArchitecture.UNKNOWN &&
            targetPlatform.architecture != runtimePlatform.architecture
        ) {
            return RuntimeDiagnostic(
                RuntimeDiagnosticCode.TARGET_MISMATCH,
                "SDK_TARGET_VALIDATE",
                "Selected SageMath runtime architecture does not match the target",
                details = mapOf("runtimePlatform" to runtimePlatform.toString(), "targetPlatform" to targetPlatform.toString()),
            )
        }
        if (targetPlatform.libc != null &&
            targetPlatform.libc != Libc.UNKNOWN &&
            runtimePlatform.libc != null &&
            runtimePlatform.libc != Libc.UNKNOWN &&
            targetPlatform.libc != runtimePlatform.libc
        ) {
            return RuntimeDiagnostic(
                RuntimeDiagnosticCode.TARGET_MISMATCH,
                "SDK_TARGET_VALIDATE",
                "Selected SageMath runtime libc does not match the target",
                details = mapOf("runtimePlatform" to runtimePlatform.toString(), "targetPlatform" to targetPlatform.toString()),
            )
        }
        return null
    }
}

fun RuntimeTarget.kindName(): String = when (this) {
    RuntimeTarget.Native -> "native"
    is RuntimeTarget.Wsl -> "wsl"
    is RuntimeTarget.Docker -> "docker"
    is RuntimeTarget.RemoteSsh -> "ssh"
}

data class RuntimePathMapping(
    val localRoot: Path,
    val targetRoot: String,
) {
    init {
        require(targetRoot.isNotBlank() && !targetRoot.contains('\u0000')) { "Target path root must be printable" }
        require(!localRoot.toString().contains('\u0000')) { "Local path root must be printable" }
    }
}

class RuntimePathMappingException(
    val diagnostic: RuntimeDiagnostic,
) : IllegalArgumentException(diagnostic.message)

class RuntimePathMapper {
    fun toTarget(localPath: Path, target: RuntimeTarget): String {
        val mapping = mappingFor(target)
            ?: if (target == RuntimeTarget.Native) return localPath.toAbsolutePath().normalize().toString()
            else throw RuntimePathMappingException(
                RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "PATH_MAP", "A non-native runtime requires an explicit path mapping"),
            )
        val localRoot = mapping.localRoot.toAbsolutePath().normalize()
        val normalized = localPath.toAbsolutePath().normalize()
        val relative = normalized.takeIf { it.startsWith(localRoot) }?.let(localRoot::relativize)
            ?: throw RuntimePathMappingException(
                RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_OUTSIDE_MAPPING, "PATH_MAP", "Local path is outside the configured runtime mapping"),
            )
        return joinTargetPath(mapping.targetRoot, relative.toString().replace('\\', '/'))
    }

    fun toLocal(targetPath: String, target: RuntimeTarget): Path {
        val mapping = mappingFor(target)
            ?: if (target == RuntimeTarget.Native) return Paths.get(targetPath)
            else throw RuntimePathMappingException(
                RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "PATH_MAP", "A non-native runtime requires an explicit path mapping"),
            )
        val normalizedTarget = normalizeTargetPath(targetPath)
        val targetRoot = normalizeTargetPath(mapping.targetRoot).trimEnd('/')
        if (normalizedTarget != targetRoot && !normalizedTarget.startsWith("$targetRoot/")) {
            throw RuntimePathMappingException(
                RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_OUTSIDE_MAPPING, "PATH_MAP", "Target path is outside the configured runtime mapping"),
            )
        }
        val relative = normalizedTarget.removePrefix(targetRoot).trimStart('/')
        return mapping.localRoot.resolve(relative.replace('/', java.io.File.separatorChar)).normalize()
    }

    private fun mappingFor(target: RuntimeTarget): RuntimePathMapping? = when (target) {
        RuntimeTarget.Native -> null
        is RuntimeTarget.Wsl -> target.pathMapping
        is RuntimeTarget.Docker -> target.pathMapping
        is RuntimeTarget.RemoteSsh -> target.pathMapping
    }

    private fun joinTargetPath(root: String, relative: String): String {
        val normalizedRoot = normalizeTargetPath(root).trimEnd('/')
        return if (relative.isEmpty()) normalizedRoot else "$normalizedRoot/${relative.trimStart('/')}"
    }

    private fun normalizeTargetPath(value: String): String {
        require(!value.contains('\u0000')) { "Target path contains a control character" }
        val normalized = value.replace('\\', '/')
        require(!normalized.startsWith("//")) {
            "Target path must not use an ambiguous UNC prefix"
        }
        val parts = normalized.split('/')
        val components = if (normalized.startsWith('/')) parts.drop(1) else parts
        require(components.none { it.isEmpty() || it == "." || it == ".." }) { "Target path contains empty or traversal components" }
        return (if (normalized.startsWith('/')) "/" else "") + components.joinToString("/")
    }
}

data class TargetProcessRequest(
    val target: RuntimeTarget,
    val executable: String,
    val args: List<String>,
    val workingDirectory: String? = null,
    val environment: Map<String, String> = emptyMap(),
    val control: RuntimeControl = RuntimeControl(),
    val maxOutputBytes: Int = 64 * 1024,
)

fun interface RuntimeTargetExecutor {
    fun execute(request: TargetProcessRequest): RuntimeProcessResult
}

/**
 * Target-aware command construction. Execution itself is injected so SSH and
 * container transports cannot be mistaken for a local ProcessBuilder probe.
 */
class JdkRuntimeTargetExecutor(
    private val local: RuntimeProcessExecutor = JdkRuntimeProcessExecutor(),
    private val remote: (TargetProcessRequest) -> RuntimeProcessResult,
) : RuntimeTargetExecutor {
    override fun execute(request: TargetProcessRequest): RuntimeProcessResult {
        val command = RuntimeTargetCommandBuilder.build(request)
        return when (request.target) {
            RuntimeTarget.Native,
            is RuntimeTarget.Wsl,
            is RuntimeTarget.Docker,
            -> local.execute(
                RuntimeProcessRequest(
                    command = command,
                    workingDirectory = request.workingDirectory?.let(Path::of),
                    environment = request.environment,
                    control = request.control,
                    maxOutputBytes = request.maxOutputBytes,
                ),
            )
            is RuntimeTarget.RemoteSsh -> remote(request)
        }
    }
}

object RuntimeTargetCommandBuilder {
    fun build(request: TargetProcessRequest): List<String> = when (val target = request.target) {
        RuntimeTarget.Native -> listOf(request.executable) + request.args
        is RuntimeTarget.Wsl -> listOf("wsl.exe", "-d", target.distribution, "--", request.executable) + request.args
        is RuntimeTarget.Docker -> listOf("docker", "run", "--rm", target.image, request.executable) + request.args
        is RuntimeTarget.RemoteSsh -> listOf("ssh", "-p", target.port.toString(), target.user?.let { "$it@${target.host}" } ?: target.host, request.executable) + request.args
    }
}

data class TargetRuntimeProbeRequest(
    val target: RuntimeTarget,
    val executable: String,
    val workingDirectory: String? = null,
    val control: RuntimeControl = RuntimeControl(),
    val maxOutputBytes: Int = 64 * 1024,
)

data class TargetRuntimeProbeResult(
    val status: RuntimeExecutionStatus,
    val version: String?,
    val expressionOutput: String?,
    val details: RuntimeProcessResult? = null,
    val diagnostics: List<RuntimeDiagnostic> = emptyList(),
)

class TargetAwareRuntimeProbe(private val executor: RuntimeTargetExecutor) {
    fun probe(request: TargetRuntimeProbeRequest): TargetRuntimeProbeResult {
        request.control.status()?.let { return TargetRuntimeProbeResult(it, null, null) }
        val version = executor.execute(
            TargetProcessRequest(
                target = request.target,
                executable = request.executable,
                args = listOf("--version"),
                workingDirectory = request.workingDirectory,
                control = request.control,
                maxOutputBytes = request.maxOutputBytes,
            ),
        )
        if (version.status != RuntimeExecutionStatus.SUCCESS || version.exitCode != 0) {
            return TargetRuntimeProbeResult(
                status = version.exitStatus(),
                version = version.standardOutput.trim().ifBlank { null },
                expressionOutput = null,
                details = version,
                diagnostics = listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_PROBE_FAILED, "TARGET_PROBE_VERSION", "Target runtime version probe failed")),
            )
        }
        val expression = executor.execute(
            TargetProcessRequest(
                target = request.target,
                executable = request.executable,
                args = listOf("-c", "print(2+2)"),
                workingDirectory = request.workingDirectory,
                control = request.control,
                maxOutputBytes = request.maxOutputBytes,
            ),
        )
        return TargetRuntimeProbeResult(
            status = expression.exitStatus(),
            version = version.standardOutput.trim().ifBlank { null },
            expressionOutput = expression.standardOutput.trim().ifBlank { null },
            details = expression,
            diagnostics = if (expression.exitStatus() == RuntimeExecutionStatus.SUCCESS) emptyList()
            else listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_PROBE_FAILED, "TARGET_PROBE_EXPRESSION", "Target runtime expression probe failed")),
        )
    }

    private fun RuntimeProcessResult.exitStatus(): RuntimeExecutionStatus = if (status != RuntimeExecutionStatus.SUCCESS) status
    else if (exitCode == 0) RuntimeExecutionStatus.SUCCESS else RuntimeExecutionStatus.FAILED
}
