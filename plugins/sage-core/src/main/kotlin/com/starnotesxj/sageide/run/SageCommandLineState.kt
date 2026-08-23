package com.starnotesxj.sageide.run

import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.CommandLineState
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessHandler
import com.intellij.execution.runners.ExecutionEnvironment
import com.starnotesxj.sageide.runtime.SageRuntimeSdkService
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import java.nio.file.Paths

/**
 * Builds the command line for one of the three execution modes:
 *
 * - NATIVE: the manifest-declared Sage launcher;
 * - WSL: `wsl.exe -d <distribution> -- bash -lc <activate environment; exec sage ...>`
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
        val mode = executionMode(s)
        val commandLine = when (mode) {
            ExecutionMode.NATIVE -> {
                val resolved = SageRuntimeSdkService.getInstance().currentExecutables(RuntimeTarget.Native)
                if (!resolved.succeeded) {
                    throw ExecutionException(resolved.diagnostics.firstOrNull()?.message ?: "The verified SageMath runtime is unavailable")
                }
                GeneralCommandLine(resolved.value!!.sage)
                    .withParameters(sageArguments)
                    .withParameters(configuration.scriptPath)
                    .withParameters(scriptArguments)
            }

            ExecutionMode.WSL -> {
                val resolved = SageRuntimeSdkService.getInstance().currentExecutables(RuntimeTarget.Wsl(s.wslDistribution))
                if (!resolved.succeeded) {
                    throw ExecutionException(resolved.diagnostics.firstOrNull()?.message ?: "The verified WSL SageMath runtime is unavailable")
                }
                val command = wslRunScript(
                    s.wslCondaEnvironment,
                    resolved.value!!.sage,
                    sageArguments + toWslPath(configuration.scriptPath) + scriptArguments,
                )
                GeneralCommandLine("wsl.exe", "-d", s.wslDistribution, "--", "bash", "-lc", command)
            }

            ExecutionMode.DOCKER -> {
                val resolved = SageRuntimeSdkService.getInstance().currentExecutables(RuntimeTarget.Docker(s.dockerImage))
                if (!resolved.succeeded) {
                    throw ExecutionException(resolved.diagnostics.firstOrNull()?.message ?: "The verified Docker SageMath runtime is unavailable")
                }
                dockerCommandLine(s, scriptArguments, resolved.value!!.sage)
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
        scriptArguments: List<String>,
        sageExecutable: String,
    ): GeneralCommandLine {
        val script = Paths.get(configuration.scriptPath)
        val scriptDir = script.parent ?: throw ExecutionException("Cannot determine the script directory")
        val scriptName = script.fileName.toString()
        return GeneralCommandLine(
            "docker", "run", "--rm",
            "-v", "$scriptDir:${s.dockerContainerDir}",
            "-w", s.dockerContainerDir,
            s.dockerImage,
            sageExecutable,
        )
            .withParameters(tokenizeArguments(s.sageParameters))
            .withParameters(scriptName)
            .withParameters(scriptArguments)
    }

    private fun executionMode(s: SageRunSettings.State): ExecutionMode =
        runCatching { ExecutionMode.valueOf(s.executionMode) }.getOrDefault(ExecutionMode.NATIVE)

}
