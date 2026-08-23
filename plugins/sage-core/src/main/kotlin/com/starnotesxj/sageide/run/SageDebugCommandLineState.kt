package com.starnotesxj.sageide.run

import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.configurations.ParamsGroup
import com.intellij.execution.runners.ExecutionEnvironment
import com.jetbrains.python.run.PythonCommandLineState
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/**
 * Python debugger-compatible state for a native Sage launch.
 *
 * Sage source is preparsed before it is executed.  The generated launcher keeps
 * the original .sage path as the code object's filename, so pydevd reports
 * breakpoints and stack frames against the editor's source file instead of a
 * generated temporary Python file.
 *
 * Native and WSL launches are supported. WSL uses a bash wrapper that activates
 * the configured environment, then runs the manifest-declared bundled Python
 * executable, converts Windows paths to /mnt paths, and maps the IDE debug client to the
 * WSL2 host gateway. Docker
 * still needs target-aware helper deployment and port/path mapping.
 */
class SageDebugCommandLineState(
    private val configuration: SageRunConfiguration,
    environment: ExecutionEnvironment,
) : PythonCommandLineState(configuration, environment) {

    private var launcherPath: Path? = null

    override fun generateCommandLine(): GeneralCommandLine {
        val settings = SageRunSettings.getInstance().getState()
        val script = Path.of(configuration.scriptPath).toAbsolutePath().normalize()
        val launcher = launcherPath ?: createLauncher(script).also { launcherPath = it }
        val executableResolution = configuration.resolveSageExecutables()
        if (!executableResolution.succeeded) {
            throw ExecutionException(
                executableResolution.diagnostics.firstOrNull()?.message
                    ?: "The selected SageMath runtime has no usable bundled Python interpreter",
            )
        }
        val executables = executableResolution.value!!
        val mode = when (executables.target) {
            com.starnotesxj.sagemath.runtime.RuntimeTarget.Native -> ExecutionMode.NATIVE
            is com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl -> ExecutionMode.WSL
            is com.starnotesxj.sagemath.runtime.RuntimeTarget.Docker -> ExecutionMode.DOCKER
            is com.starnotesxj.sagemath.runtime.RuntimeTarget.RemoteSsh ->
                throw ExecutionException("SSH SageMath debugging requires a target transport")
        }
        val bundledPython = executables.python
            ?: throw ExecutionException("The verified SageMath runtime has no usable bundled Python interpreter")
        val commandLine = if (mode == ExecutionMode.WSL) {
            GeneralCommandLine(
                "wsl.exe", "-d", settings.wslDistribution, "--", "bash", "-lc",
                wslDebugScript(settings.wslCondaEnvironment, executables.sage, bundledPython),
                // bash -c uses the next item as $0; the debugger's injected
                // arguments follow it and are forwarded by wslDebugScript.
                "sage-debug-entry",
            )
        } else {
            GeneralCommandLine(executables.sage)
                .withWorkDirectory(script.parent?.toString())
        }
        PythonCommandLineState.createStandardGroups(commandLine)

        val executableOptions = commandLine.parametersList.getParamsGroup(EXE_OPTIONS)
            ?: ParamsGroup(EXE_OPTIONS)
        executableOptions.addParameters(tokenizeArguments(settings.sageParameters))
        if (mode != ExecutionMode.WSL) {
            executableOptions.addParameter("-python")
        }

        // PyDebugRunner adds pydevd and --file to the Debugger group.  The
        // launcher is therefore the first Script-group argument consumed by
        // pydevd's --file option; the .sage path and user args reach the
        // launcher as sys.argv[1..].
        val scriptGroup = commandLine.parametersList.getParamsGroup(SCRIPT)
            ?: ParamsGroup(SCRIPT)
        scriptGroup.addParameter(launcher.toString())
        scriptGroup.addParameter(script.toString())
        scriptGroup.addParameters(tokenizeArguments(configuration.scriptParameters))
        return commandLine
    }

    private fun createLauncher(script: Path): Path {
        val launcher = Files.createTempFile("sage-pycharm-debug-", ".py")
        launcher.toFile().deleteOnExit()
        Files.writeString(launcher, LAUNCHER_SOURCE, StandardCharsets.UTF_8)
        return launcher
    }

    private companion object {
        const val EXE_OPTIONS = "Exe Options"
        const val SCRIPT = "Script"

        val LAUNCHER_SOURCE = """
            import pathlib
            import sys
            from sage.repl.preparse import preparse

            target = pathlib.Path(sys.argv[1]).resolve()
            source = target.read_text(encoding="utf-8")
            sys.argv = [str(target), *sys.argv[2:]]
            namespace = {
                "__name__": "__main__",
                "__file__": str(target),
                "__package__": None,
            }
            code = compile(preparse(source), str(target), "exec")
            exec(code, namespace, namespace)
        """.trimIndent()
    }
}

/** Shell-style argument parsing shared by Sage run/debug command builders. */
internal fun tokenizeArguments(value: String): List<String> =
    com.intellij.util.execution.ParametersListUtil.parse(value)
