package com.starnotesxj.sageide.run

import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.CommandLineState
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.OSProcessHandler
import com.intellij.execution.process.ProcessHandler
import com.intellij.execution.runners.ExecutionEnvironment
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
        val resolved = configuration.resolveSageExecutables()
        if (!resolved.succeeded) {
            throw ExecutionException(resolved.diagnostics.firstOrNull()?.message ?: "The selected SageMath runtime is unavailable")
        }
        val executables = resolved.value!!
        val mode = when (executables.target) {
            com.starnotesxj.sagemath.runtime.RuntimeTarget.Native -> ExecutionMode.NATIVE
            is com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl -> ExecutionMode.WSL
            is com.starnotesxj.sagemath.runtime.RuntimeTarget.Docker -> ExecutionMode.DOCKER
            is com.starnotesxj.sagemath.runtime.RuntimeTarget.RemoteSsh ->
                throw ExecutionException("SSH SageMath execution requires a target transport")
        }
        val commandLine = when (mode) {
            ExecutionMode.NATIVE -> GeneralCommandLine(executables.sage)
                .withParameters(sageArguments)
                .withParameters(configuration.scriptPath)
                .withParameters(scriptArguments)

            ExecutionMode.WSL -> {
                val target = executables.target as com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl
                val command = wslRunScript(
                    s.wslCondaEnvironment,
                    executables.sage,
                    sageArguments + toWslPath(configuration.scriptPath) + scriptArguments,
                    s.wslCondaExecutable,
                )
                GeneralCommandLine("wsl.exe", "-d", target.distribution, "--exec", "/bin/bash", "-lc", command)
            }

            ExecutionMode.DOCKER -> dockerCommandLine(s, scriptArguments, executables.sage)
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

}
