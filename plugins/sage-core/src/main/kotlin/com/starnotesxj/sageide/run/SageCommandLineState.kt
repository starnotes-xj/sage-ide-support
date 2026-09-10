package com.starnotesxj.sageide.run

import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.CommandLineState
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessHandler
import java.nio.file.Files
import com.intellij.execution.runners.ExecutionEnvironment
import com.starnotesxj.sagemath.runtime.ContainerCommandBuilder
import com.starnotesxj.sagemath.runtime.ContainerEngine
import com.starnotesxj.sagemath.runtime.ContainerRunSpec
import com.starnotesxj.sagemath.runtime.RuntimePathMapper
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import com.starnotesxj.sagemath.runtime.SshOpenSshCommandBuilder
import com.starnotesxj.sagemath.runtime.SshSageRunRequest
import com.starnotesxj.sageide.type.SageLiveTypeSnapshotService
import com.starnotesxj.sageide.type.SageRunTypeFeedbackSession
import java.nio.file.Path
import java.nio.file.Paths

/**
 * Builds the command line for one of the three execution modes:
 *
 * - NATIVE: the manifest-declared Sage launcher;
 * - WSL: `wsl.exe -d <distribution> -- <sageExecutable> <script> <args>`
 * - DOCKER: `docker run --rm -v <scriptDir>:<containerDir> -w <containerDir>
 *   <image> <dockerCommand> <scriptName> <args>` — the script directory is
 *   mounted into the container, so host/container path mapping is automatic.
 */
class SageCommandLineState(
    private val configuration: SageRunConfiguration,
    environment: ExecutionEnvironment,
) : CommandLineState(environment) {

    override fun startProcess(): ProcessHandler {
        val s = SageRunSettings.getInstance().getState()
        val scriptArguments = tokenizeArguments(configuration.scriptParameters)
        val sageArguments = tokenizeArguments(s.sageParameters)
        val usesConfiguredWsl = configuration.usesConfiguredWslRuntime(s)
        val resolved = if (usesConfiguredWsl) null else configuration.resolveSageExecutables()
        if (resolved != null && !resolved.succeeded) {
            throw ExecutionException(resolved.diagnostics.firstOrNull()?.message ?: "The selected SageMath runtime is unavailable")
        }
        val executables = resolved?.value
        val mode = if (usesConfiguredWsl) {
            ExecutionMode.WSL
        } else {
            when (executables!!.target) {
                com.starnotesxj.sagemath.runtime.RuntimeTarget.Native -> ExecutionMode.NATIVE
                is com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl -> ExecutionMode.WSL
                is RuntimeTarget.Docker -> ExecutionMode.DOCKER
                is com.starnotesxj.sagemath.runtime.RuntimeTarget.RemoteSsh -> ExecutionMode.SSH
            }
        }
        var runFeedback: SageRunTypeFeedbackSession? = null
        val commandLine = when (mode) {
            ExecutionMode.NATIVE -> {
                val sageExecutable = executables!!.sage
                runFeedback = prepareRunFeedback(s, SageLiveTypeSnapshotService.runtimeKey(RuntimeTarget.Native, sageExecutable))
                GeneralCommandLine(sageExecutable).apply {
                    runFeedback?.let { withEnvironment(it.nativeEnvironment()) }
                    withParameters(sageArguments)
                    withParameters(configuration.scriptPath)
                    withParameters(scriptArguments)
                }
            }

            ExecutionMode.WSL -> {
                val distribution = if (usesConfiguredWsl) {
                    s.wslDistribution
                } else {
                    (executables!!.target as com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl).distribution
                }
                val arguments = sageArguments + toWslPath(configuration.scriptPath) + scriptArguments
                // The executable is populated by the post-startup discovery.
                // Keep the launch command direct even if the user runs a file
                // before discovery finishes; a missing `sage` then fails fast
                // instead of showing a long Conda discovery script in the console.
                val sageExecutable = if (usesConfiguredWsl) {
                    configuredWslSageExecutable(s) ?: "sage"
                } else {
                    executables!!.sage
                }
                runFeedback = prepareRunFeedback(
                    s,
                    SageLiveTypeSnapshotService.runtimeKey(RuntimeTarget.Wsl(distribution), sageExecutable),
                )
                GeneralCommandLine("wsl.exe")
                    .apply {
                        val feedback = runFeedback
                        if (feedback != null) {
                            withEnvironment(feedback.wslEnvironment())
                            withParameters(
                                listOf(
                                    "-d",
                                    distribution,
                                    "--exec",
                                    "/bin/sh",
                                    "-c",
                                    SageRunTypeFeedbackSession.WSL_BOOTSTRAP_COMMAND,
                                    "sage-ide-run-feedback",
                                    sageExecutable,
                                ) + arguments,
                            )
                        } else {
                            withParameters(wslDirectRunArguments(distribution, sageExecutable, arguments))
                        }
                    }
            }

            ExecutionMode.DOCKER -> {
                val target = executables!!.target as RuntimeTarget.Docker
                dockerCommandLine(s, target.engine, scriptArguments)
            }

            ExecutionMode.SSH -> {
                val target = executables!!.target as RuntimeTarget.RemoteSsh
                val transport = SageRuntimeService.getInstance().resolveSshTransportSpec(s, target)
                if (!transport.succeeded) {
                    throw ExecutionException(transport.diagnostics.firstOrNull()?.message ?: "SSH transport settings are invalid")
                }
                val mapping = target.pathMapping ?: throw ExecutionException("SSH path mapping is required")
                val script = runCatching { Path.of(configuration.scriptPath).toAbsolutePath().normalize() }.getOrElse {
                    throw ExecutionException("SSH script path is invalid: ${configuration.scriptPath}", it)
                }
                if (!Files.isRegularFile(script) || script == mapping.localRoot.toAbsolutePath().normalize()) {
                    throw ExecutionException("SSH Sage script must be an existing regular file inside the configured local mapping")
                }
                val remoteScript = runCatching { RuntimePathMapper().toTarget(script, target) }.getOrElse {
                    throw ExecutionException("SSH script path is outside the configured mapping: ${it.message}", it)
                }
                val request = runCatching {
                    SshSageRunRequest(
                        transport = transport.value!!,
                        remoteSageExecutable = executables.sage,
                        remoteScriptPath = remoteScript,
                        sageArguments = sageArguments,
                        scriptArguments = scriptArguments,
                    )
                }.getOrElse {
                    throw ExecutionException("SSH Sage run request is invalid: ${it.message}", it)
                }
                GeneralCommandLine(SshOpenSshCommandBuilder.build(request))
            }
        }
        val handler = try {
            OSProcessHandler(commandLine)
        }
        catch (e: ExecutionException) {
            runFeedback?.close()
            throw ExecutionException("Failed to start sage: ${e.message}", e)
        }
        runFeedback?.attach(handler, configuration.project)
        return handler
    }

    private fun prepareRunFeedback(settings: SageRunSettings.State, runtimeKey: String): SageRunTypeFeedbackSession? =
        if (settings.liveTypeProbingEnabled) SageRunTypeFeedbackSession.prepare(configuration.scriptPath, runtimeKey) else null

    private fun dockerCommandLine(
        s: SageRunSettings.State,
        engine: ContainerEngine,
        scriptArguments: List<String>,
    ): GeneralCommandLine {
        val script = Paths.get(configuration.scriptPath)
        val scriptDir = script.parent ?: throw ExecutionException("Cannot determine the script directory")
        val scriptName = script.fileName.toString()
        val spec = ContainerRunSpec(
            engine = engine,
            image = s.dockerImage,
            containerCommand = s.dockerCommand,
            hostScriptDirectory = scriptDir,
            containerWorkingDirectory = s.dockerContainerDir,
            scriptFileName = scriptName,
            sageArguments = tokenizeArguments(s.sageParameters),
            scriptArguments = scriptArguments,
        )
        return GeneralCommandLine(ContainerCommandBuilder.build(spec))
    }

}
