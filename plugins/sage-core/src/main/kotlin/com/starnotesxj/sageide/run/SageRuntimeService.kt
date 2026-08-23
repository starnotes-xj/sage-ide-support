package com.starnotesxj.sageide.run

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.starnotesxj.sagemath.runtime.JdkRuntimeProcessExecutor
import com.starnotesxj.sagemath.runtime.MutableRuntimeCancellation
import com.starnotesxj.sagemath.runtime.RuntimeControl
import com.starnotesxj.sagemath.runtime.RuntimeDeadline
import com.starnotesxj.sagemath.runtime.RuntimeExecutionStatus
import com.starnotesxj.sagemath.runtime.RuntimeProbe
import com.starnotesxj.sagemath.runtime.RuntimeProbeRequest
import com.starnotesxj.sagemath.runtime.RuntimeProbeResult
import com.starnotesxj.sagemath.runtime.ResolvedRuntimeExecutables
import com.starnotesxj.sagemath.runtime.RuntimeDiagnostic
import com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode
import com.starnotesxj.sagemath.runtime.RuntimeOperationResult
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import java.nio.file.Path
import java.time.Duration
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ThreadFactory
import java.util.concurrent.atomic.AtomicInteger

/** Application-scoped adapter for Sage discovery and managed-runtime probes. */
@Service(Service.Level.APP)
class SageRuntimeService : Disposable {
    private val executor: ExecutorService = Executors.newCachedThreadPool(SageThreadFactory)
    private val probeExecutor = JdkRuntimeProcessExecutor()
    private val probe = RuntimeProbe(probeExecutor)

    fun probeAsync(
        executable: Path,
        deadline: Duration = DEFAULT_PROBE_DEADLINE,
        maxOutputBytes: Int = DEFAULT_PROBE_OUTPUT_BYTES,
    ): SageRuntimeProbeHandle<RuntimeProbeResult> {
        require(!deadline.isNegative && !deadline.isZero) { "Runtime probe deadline must be positive" }
        require(maxOutputBytes > 0) { "Runtime probe output limit must be positive" }
        val cancellation = MutableRuntimeCancellation()
        val control = RuntimeControl(RuntimeDeadline.after(deadline), cancellation)
        val future = CompletableFuture.supplyAsync({
            probe.probe(RuntimeProbeRequest(executable, control = control, maxOutputBytes = maxOutputBytes))
        }, executor)
        return SageRuntimeProbeHandle(future, cancellation)
    }

    /** Resolves a configured native executable, falling back to PATH discovery. */
    fun resolveNativeExecutable(configuredExecutable: String): String? {
        return configuredExecutable.trim().takeIf { it.isNotEmpty() } ?: SageAutoDetect.detectNativeSage()
    }

    /** Resolves an externally managed Sage installation inside WSL Conda. */
    fun resolveWslExecutables(
        distribution: String,
        condaEnvironment: String,
        condaExecutable: String,
        sageExecutable: String,
        deadline: Duration = DEFAULT_PROBE_DEADLINE,
    ): RuntimeOperationResult<ResolvedRuntimeExecutables> {
        require(!deadline.isNegative && !deadline.isZero) { "WSL runtime probe deadline must be positive" }
        val runtime = SageAutoDetect.detectWslRuntime(
            distribution,
            condaEnvironment,
            condaExecutable,
            sageExecutable,
            timeoutMillis = deadline.toMillis().coerceAtLeast(1),
        )
            ?: return RuntimeOperationResult(
                null,
                listOf(
                    RuntimeDiagnostic(
                        RuntimeDiagnosticCode.TARGET_PROBE_FAILED,
                        "WSL_RUNTIME_RESOLVE",
                        "WSL Sage/Conda could not be discovered or activated",
                        details = mapOf("distribution" to distribution, "condaEnvironment" to condaEnvironment.ifBlank { "sage" }),
                    ),
                ),
                false,
            )
        val python = runtime.pythonExecutable
            ?: return RuntimeOperationResult(
                null,
                listOf(
                    RuntimeDiagnostic(
                        RuntimeDiagnosticCode.RUNTIME_PYTHON_UNAVAILABLE,
                        "WSL_RUNTIME_RESOLVE",
                        "The WSL Conda Sage environment does not expose a Python interpreter",
                        details = mapOf("sageExecutable" to runtime.sageExecutable),
                    ),
                ),
                false,
            )
        return RuntimeOperationResult(
            ResolvedRuntimeExecutables(
                sage = runtime.sageExecutable,
                python = python,
                runtimeRoot = null,
                target = RuntimeTarget.Wsl(runtime.distribution),
            ),
        )
    }

    fun probeConfiguredNativeAsync(
        configuredExecutable: String,
        deadline: Duration = DEFAULT_PROBE_DEADLINE,
    ): SageRuntimeProbeHandle<RuntimeProbeResult>? {
        val executable = resolveNativeExecutable(configuredExecutable) ?: return null
        return probeAsync(Path.of(executable), deadline)
    }

    /** Detects and validates native Sage; WSL now probes the configured Conda environment. */
    fun detectAndProbeAsync(
        mode: ExecutionMode,
        wslDistribution: String,
        deadline: Duration = DEFAULT_PROBE_DEADLINE,
    ): SageRuntimeProbeHandle<SageRuntimeDetectionResult> {
        require(!deadline.isNegative && !deadline.isZero) { "Runtime probe deadline must be positive" }
        val cancellation = MutableRuntimeCancellation()
        val control = RuntimeControl(RuntimeDeadline.after(deadline), cancellation)
        val future = CompletableFuture.supplyAsync({
            when (mode) {
                ExecutionMode.NATIVE -> {
                    val executable = SageAutoDetect.detectNativeSage()
                    if (executable.isNullOrBlank()) {
                        SageRuntimeDetectionResult(mode, null, null, "Native Sage executable was not found")
                    } else {
                        val result = probe.probe(RuntimeProbeRequest(Path.of(executable), control = control))
                        SageRuntimeDetectionResult(
                            mode,
                            executable,
                            result,
                            if (result.status == RuntimeExecutionStatus.SUCCESS) {
                                "Validated " + executable
                            } else {
                                "Sage probe failed with " + result.status
                            },
                        )
                    }
                }
                ExecutionMode.WSL -> {
                    val state = SageRunSettings.getInstance().getState()
                    val runtime = SageAutoDetect.detectWslRuntime(
                        distribution = wslDistribution,
                        condaEnvironment = state.wslCondaEnvironment,
                        condaExecutable = state.wslCondaExecutable,
                        sageExecutable = state.sageExecutable,
                        timeoutMillis = deadline.toMillis().coerceAtLeast(1),
                    )
                    SageRuntimeDetectionResult(
                        mode,
                        runtime?.sageExecutable,
                        null,
                        if (runtime == null) {
                            "WSL Sage/Conda environment was not found or could not be activated"
                        } else {
                            "Validated WSL Sage ${runtime.version ?: "runtime"} in conda environment '${runtime.condaEnvironment}'"
                        },
                    )
                }
                ExecutionMode.DOCKER -> {
                    val image = SageAutoDetect.detectDockerImage()
                    SageRuntimeDetectionResult(
                        mode,
                        image,
                        null,
                        if (image == null) {
                            "Sage Docker image was not found"
                        } else {
                            "Docker Sage image discovered; target-aware probe is not available yet"
                        },
                    )
                }
            }
        }, executor)
        return SageRuntimeProbeHandle(future, cancellation)
    }

    override fun dispose() {
        executor.shutdownNow()
    }

    companion object {
        val DEFAULT_PROBE_DEADLINE: Duration = Duration.ofSeconds(10)
        const val DEFAULT_PROBE_OUTPUT_BYTES: Int = 64 * 1024

        @JvmStatic
        fun getInstance(): SageRuntimeService = ApplicationManager.getApplication().getService(SageRuntimeService::class.java)
    }

    private object SageThreadFactory : ThreadFactory {
        private val counter = AtomicInteger()
        override fun newThread(runnable: Runnable): Thread = Thread(runnable, "sage-runtime-service-" + counter.incrementAndGet()).apply { isDaemon = true }
    }
}

data class SageRuntimeDetectionResult(
    val mode: ExecutionMode,
    val discoveredValue: String?,
    val probe: RuntimeProbeResult?,
    val diagnostic: String?,
) {
    val isReady: Boolean
        get() = when (mode) {
            ExecutionMode.NATIVE -> probe?.status == RuntimeExecutionStatus.SUCCESS
            ExecutionMode.WSL, ExecutionMode.DOCKER -> !discoveredValue.isNullOrBlank()
        }
}

class SageRuntimeProbeHandle<T> internal constructor(
    val future: CompletableFuture<T>,
    private val cancellation: MutableRuntimeCancellation,
) {
    fun cancel() {
        cancellation.cancel()
    }
}
