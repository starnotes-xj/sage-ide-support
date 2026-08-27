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
        val commandLine = when (mode) {
            ExecutionMode.NATIVE -> GeneralCommandLine(executables!!.sage)
                .withParameters(sageArguments)
                .withParameters(configuration.scriptPath)
                .withParameters(scriptArguments)

            ExecutionMode.WSL -> {
                val distribution = if (usesConfiguredWsl) {
                    s.wslDistribution
                } else {
                    (executables!!.target as com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl).distribution
                }
                val arguments = sageArguments + toWslPath(configuration.scriptPath) + scriptArguments
                val sageExecutable = if (usesConfiguredWsl) {
                    configuredWslSageExecutable(s)
                        ?: throw ExecutionException("The Sage executable is not configured for WSL")
                } else {
                    executables!!.sage
                }
                // Use WSL's direct executable form rather than `bash -lc`. This
                // keeps IntelliJ's console command readable and leaves only Sage
                // stdout/stderr visible after the command line.
                GeneralCommandLine("wsl.exe")
                    .withParameters(wslDirectRunArguments(distribution, sageExecutable, arguments))
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
        return try {
            OSProcessHandler(commandLine)
        }
        catch (e: ExecutionException) {
            throw ExecutionException("Failed to start sage: ${e.message}", e)
        }
    }

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
