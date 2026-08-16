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
 * - NATIVE: `sage <script> <args>`
 * - WSL: `wsl.exe -d <distribution> -- sage <script> <args>`
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
        val scriptArguments = configuration.scriptParameters.split(" ").filter { it.isNotBlank() }
        val sageArguments = s.sageParameters.split(" ").filter { it.isNotBlank() }
        val commandLine = when (executionMode(s)) {
            ExecutionMode.NATIVE -> GeneralCommandLine(s.sageExecutable)
                .withParameters(sageArguments)
                .withParameters(configuration.scriptPath)
                .withParameters(scriptArguments)

            ExecutionMode.WSL -> {
                val sagePath = s.sageExecutable
                if (sagePath.isBlank() || sagePath.startsWith("~")) {
                    throw ExecutionException(
                        "The Sage executable is not configured for WSL. " +
                        "Open Settings | Tools | SageMath and use \"Detect Sage installation\"."
                    )
                }
                GeneralCommandLine("wsl.exe", "-d", s.wslDistribution, "--", sagePath)
                    .withParameters(sageArguments)
                    .withParameters(toWslPath(configuration.scriptPath))
                    .withParameters(scriptArguments)
            }

            ExecutionMode.DOCKER -> dockerCommandLine(s, scriptArguments)
        }
        return try {
            OSProcessHandler(commandLine)
        }
        catch (e: ExecutionException) {
            throw ExecutionException("Failed to start sage: ${e.message}", e)
        }
    }

    private fun dockerCommandLine(s: SageRunSettings.State, scriptArguments: List<String>): GeneralCommandLine {
        val script = Paths.get(configuration.scriptPath)
        val scriptDir = script.parent ?: throw ExecutionException("Cannot determine the script directory")
        val scriptName = script.fileName.toString()
        return GeneralCommandLine(
            "docker", "run", "--rm",
            "-v", "$scriptDir:${s.dockerContainerDir}",
            "-w", s.dockerContainerDir,
            s.dockerImage,
            s.dockerCommand,
        )
            .withParameters(s.sageParameters.split(" ").filter { it.isNotBlank() })
            .withParameters(scriptName)
            .withParameters(scriptArguments)
    }

    private fun executionMode(s: SageRunSettings.State): ExecutionMode =
        runCatching { ExecutionMode.valueOf(s.executionMode) }.getOrDefault(ExecutionMode.NATIVE)

    /** `C:\Users\星记\a.sage` -> `/mnt/c/Users/星记/a.sage` for execution inside WSL. */
    private fun toWslPath(windowsPath: String): String {
        val normalized = windowsPath.replace('\\', '/')
        val match = Regex("^([A-Za-z]):/(.*)$").matchEntire(normalized) ?: return normalized
        return "/mnt/${match.groupValues[1].lowercase()}/${match.groupValues[2]}"
    }
}
