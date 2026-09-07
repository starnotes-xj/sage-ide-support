package com.starnotesxj.sageide.run

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.starnotesxj.sagemath.runtime.ContainerRuntimeProbe
import com.starnotesxj.sagemath.runtime.JdkContainerRuntimeExecutor
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
import com.starnotesxj.sagemath.runtime.RuntimePathMapping
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import com.starnotesxj.sagemath.runtime.SshAuthentication
import com.starnotesxj.sagemath.runtime.SshOpenSshSpec
import com.starnotesxj.sagemath.runtime.SshSageRunRequest
import java.nio.file.Files
import java.nio.file.Path
import java.time.Duration
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ThreadFactory
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicInteger

/** Application-scoped adapter for Sage discovery and managed-runtime probes. */
@Service(Service.Level.APP)
class SageRuntimeService : Disposable {
    private val executor: ExecutorService = Executors.newCachedThreadPool(SageThreadFactory)
    private val probeExecutor = JdkRuntimeProcessExecutor()
    private val probe = RuntimeProbe(probeExecutor)
    private val containerProbe = ContainerRuntimeProbe(JdkContainerRuntimeExecutor(probeExecutor))
    private val discoveryStarted = AtomicBoolean(false)

    /**
     * Starts the one-time post-install discovery without blocking project startup.
     * The resulting paths are persisted only into still-empty settings fields, so
     * a user's explicit runtime choice is never replaced.
     */
    fun discoverInstalledRuntimesAsync(): SageRuntimeProbeHandle<DetectedSageRuntimes>? {
        if (!discoveryStarted.compareAndSet(false, true)) return null
        val cancellation = MutableRuntimeCancellation()
        val future = CompletableFuture.supplyAsync({
            SageAutoDetect.detectInstalledRuntimes(DEFAULT_DISCOVERY_TIMEOUT_MILLIS)
        }, executor)
        future.whenComplete { detected, error ->
            if (error == null && detected != null && !cancellation.isCancelled()) {
                persistDetectedRuntimes(detected)
            }
        }
        return SageRuntimeProbeHandle(future, cancellation)
    }

    private fun persistDetectedRuntimes(detected: DetectedSageRuntimes) {
        val settings = SageRunSettings.getInstance()
        val state = settings.getState()
        if (state.nativeSageExecutable.isBlank() && detected.nativeExecutable != null) {
            state.nativeSageExecutable = detected.nativeExecutable
        }
        val wsl = detected.wslRuntimes.firstOrNull()
        if (wsl != null) {
            if (state.wslSageExecutable.isBlank()) state.wslSageExecutable = wsl.sageExecutable
            if (state.wslPythonExecutable.isBlank()) {
                state.wslPythonExecutable = wsl.pythonExecutable.orEmpty()
            }
            if (state.wslCondaExecutable.isBlank()) state.wslCondaExecutable = wsl.condaExecutable.orEmpty()
            if (state.wslDistribution.isBlank()) state.wslDistribution = wsl.distribution
            if (state.wslCondaEnvironment.isBlank()) state.wslCondaEnvironment = wsl.condaEnvironment
        }
        settings.loadState(state)
    }

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

    fun resolveNativeExecutables(configuredExecutable: String): RuntimeOperationResult<ResolvedRuntimeExecutables> {
        val executable = resolveNativeExecutable(configuredExecutable)
            ?: return RuntimeOperationResult(
                null,
                listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED, "NATIVE_RUNTIME_RESOLVE", "Native Sage executable was not found")),
                false,
            )
        return RuntimeOperationResult(
            ResolvedRuntimeExecutables(executable, null, null, RuntimeTarget.Native),
        )
    }

    fun <T> submit(task: (RuntimeControl) -> T): SageRuntimeProbeHandle<T> {
        val cancellation = MutableRuntimeCancellation()
        val control = RuntimeControl(RuntimeDeadline.after(DEFAULT_PROBE_DEADLINE), cancellation)
        return SageRuntimeProbeHandle(
            CompletableFuture.supplyAsync({ task(control) }, executor),
            cancellation,
        )
    }

    fun probeConfiguredNative(
        configuredExecutable: String,
        control: RuntimeControl,
    ): RuntimeProbeResult? {
        val executable = resolveNativeExecutable(configuredExecutable) ?: return null
        return probe.probe(RuntimeProbeRequest(Path.of(executable), control = control, maxOutputBytes = DEFAULT_PROBE_OUTPUT_BYTES))
    }

    fun validateContainerProfile(settings: SageRunSettings.State): RuntimeOperationResult<Any> {
        val profile = com.starnotesxj.sagemath.runtime.ContainerProfileValidator.validate(
            settings.containerExecutable,
            settings.dockerImage,
            settings.dockerCommand,
            settings.dockerContainerDir,
        )
        return if (profile.succeeded) RuntimeOperationResult(Unit) else RuntimeOperationResult(null, profile.diagnostics, false)
    }

    fun validateSshSettings(settings: SageRunSettings.State): RuntimeOperationResult<Any> {
        val resolved = resolveSshExecutables(settings)
        return if (resolved.succeeded) RuntimeOperationResult(Unit) else RuntimeOperationResult(null, resolved.diagnostics, false)
    }

    fun resolveContainerExecutables(
        settings: SageRunSettings.State,
        deadline: Duration = DEFAULT_PROBE_DEADLINE,
        control: RuntimeControl? = null,
    ): RuntimeOperationResult<ResolvedRuntimeExecutables> {
        require(!deadline.isNegative && !deadline.isZero) { "Container probe deadline must be positive" }
        val profile = com.starnotesxj.sagemath.runtime.ContainerProfileValidator.validate(
            settings.containerExecutable,
            settings.dockerImage,
            settings.dockerCommand,
            settings.dockerContainerDir,
        )
        if (!profile.succeeded) return RuntimeOperationResult(null, profile.diagnostics, false)
        val engine = profile.value!!
        val probeControl = control ?: RuntimeControl(RuntimeDeadline.after(deadline), MutableRuntimeCancellation())
        val probeResult = containerProbe.probe(
            engine = engine,
            image = settings.dockerImage.trim(),
            command = settings.dockerCommand.trim(),
            control = probeControl,
            maxOutputBytes = DEFAULT_PROBE_OUTPUT_BYTES,
        )
        if (probeResult.status != RuntimeExecutionStatus.SUCCESS || probeResult.expressionOutput != "4") {
            return RuntimeOperationResult(null, probeResult.diagnostics.ifEmpty {
                listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_PROBE_FAILED, "CONTAINER_RESOLVE", "Container Sage image probe failed"))
            }, false)
        }
        return RuntimeOperationResult(
            ResolvedRuntimeExecutables(
                sage = settings.dockerCommand.trim(),
                python = null,
                runtimeRoot = null,
                target = RuntimeTarget.Docker(settings.dockerImage.trim(), engine = engine),
            ),
        )
    }

    fun resolveSshExecutables(settings: SageRunSettings.State): RuntimeOperationResult<ResolvedRuntimeExecutables> {
        val knownHosts = runCatching { Path.of(settings.sshKnownHostsFile.trim()) }.getOrElse {
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_KNOWN_HOSTS_VALIDATE", "SSH known_hosts path is invalid")), false)
        }
        val localRoot = runCatching { Path.of(settings.sshLocalRoot.trim()) }.getOrElse {
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "SSH_PATH_MAPPING_VALIDATE", "SSH local mapping root is invalid")), false)
        }
        val mapping = runCatching {
            RuntimePathMapping(localRoot, settings.sshTargetRoot.trim())
        }.getOrElse { error ->
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "SSH_PATH_MAPPING_VALIDATE", error.message ?: "SSH path mapping is invalid")), false)
        }
        val authentication = when (settings.sshAuthentication.trim().uppercase()) {
            "AGENT" -> SshAuthentication.Agent
            "IDENTITY_FILE" -> SshAuthentication.IdentityFile(runCatching { Path.of(settings.sshIdentityFile.trim()) }.getOrElse {
                return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_AUTH_VALIDATE", "SSH identity file path is invalid")), false)
            })
            else -> return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_AUTH_VALIDATE", "SSH authentication must be AGENT or IDENTITY_FILE")), false)
        }
        val target = RuntimeTarget.RemoteSsh(
            host = settings.sshHost.trim(),
            user = settings.sshUser.trim().takeIf { it.isNotEmpty() },
            port = settings.sshPort,
            pathMapping = mapping,
            runtimeRoot = settings.sshRuntimeRoot.trim(),
        )
        val spec = runCatching {
            SshOpenSshSpec(
                host = target.host,
                user = target.user,
                port = target.port,
                knownHostsFile = knownHosts,
                authentication = authentication,
                runtimeRoot = target.runtimeRoot!!,
                pathMapping = mapping,
                connectTimeout = Duration.ofSeconds(settings.sshConnectTimeoutSeconds.toLong()),
            )
        }.getOrElse { error ->
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_CONFIG_VALIDATE", error.message ?: "SSH settings are invalid")), false)
        }
        if (!Files.isRegularFile(knownHosts, java.nio.file.LinkOption.NOFOLLOW_LINKS) || !knownHosts.isAbsolute) {
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_KNOWN_HOSTS_VALIDATE", "SSH known_hosts must be an absolute regular file")), false)
        }
        val remoteSage = settings.sshSageExecutable.trim()
        if (remoteSage.isBlank()) {
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "SSH_RUNTIME_ROOT_VALIDATE", "SSH Sage executable path is required")), false)
        }
        val requestValidation = runCatching {
            SshSageRunRequest(spec, remoteSage, "${mapping.targetRoot}/.sage-run-validation.sage")
        }.exceptionOrNull()
        if (requestValidation != null) {
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "SSH_RUNTIME_ROOT_VALIDATE", requestValidation.message ?: "SSH Sage executable is outside runtime root")), false)
        }
        return RuntimeOperationResult(
            ResolvedRuntimeExecutables(
                sage = remoteSage,
                python = null,
                runtimeRoot = spec.runtimeRoot,
                target = target,
            ),
        )
    }

    fun resolveSshTransportSpec(settings: SageRunSettings.State, target: RuntimeTarget.RemoteSsh): RuntimeOperationResult<SshOpenSshSpec> {
        val knownHosts = runCatching { Path.of(settings.sshKnownHostsFile.trim()) }.getOrElse {
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_KNOWN_HOSTS_VALIDATE", "SSH known_hosts path is invalid")), false)
        }
        val localRoot = runCatching { Path.of(settings.sshLocalRoot.trim()) }.getOrElse {
            return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "SSH_PATH_MAPPING_VALIDATE", "SSH local mapping root is invalid")), false)
        }
        val mapping = target.pathMapping ?: return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "SSH_PATH_MAPPING_VALIDATE", "SSH path mapping is required")), false)
        val authentication = when (settings.sshAuthentication.trim().uppercase()) {
            "AGENT" -> SshAuthentication.Agent
            "IDENTITY_FILE" -> SshAuthentication.IdentityFile(runCatching { Path.of(settings.sshIdentityFile.trim()) }.getOrElse {
                return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_AUTH_VALIDATE", "SSH identity file path is invalid")), false)
            })
            else -> return RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_AUTH_VALIDATE", "SSH authentication must be AGENT or IDENTITY_FILE")), false)
        }
        return runCatching {
            SshOpenSshSpec(target.host, target.user, target.port, knownHosts, authentication, target.runtimeRoot!!, RuntimePathMapping(localRoot, mapping.targetRoot), Duration.ofSeconds(settings.sshConnectTimeoutSeconds.toLong()))
        }.fold(
            onSuccess = { RuntimeOperationResult(it) },
            onFailure = { RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "SSH_CONFIG_VALIDATE", it.message ?: "SSH transport settings are invalid")), false) },
        )
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

    override fun dispose() {
        executor.shutdownNow()
    }

    companion object {
        val DEFAULT_PROBE_DEADLINE: Duration = Duration.ofSeconds(10)
        const val DEFAULT_DISCOVERY_TIMEOUT_MILLIS: Long = 10_000
        const val DEFAULT_PROBE_OUTPUT_BYTES: Int = 64 * 1024

        @JvmStatic
        fun getInstance(): SageRuntimeService = ApplicationManager.getApplication().getService(SageRuntimeService::class.java)
    }

    private object SageThreadFactory : ThreadFactory {
        private val counter = AtomicInteger()
        override fun newThread(runnable: Runnable): Thread = Thread(runnable, "sage-runtime-service-" + counter.incrementAndGet()).apply { isDaemon = true }
    }
}

class SageRuntimeProbeHandle<T> internal constructor(
    val future: CompletableFuture<T>,
    private val cancellation: MutableRuntimeCancellation,
) {
    fun cancel() {
        cancellation.cancel()
        future.cancel(true)
    }
}
