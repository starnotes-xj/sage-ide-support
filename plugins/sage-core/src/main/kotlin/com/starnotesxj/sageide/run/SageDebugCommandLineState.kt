package com.starnotesxj.sageide.run

import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.configurations.ParamsGroup
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.vfs.encoding.EncodingProjectManager
import com.jetbrains.python.sdk.PythonSdkType
import com.jetbrains.python.run.PythonCommandLineState
import com.jetbrains.python.run.PythonExecution
import com.jetbrains.python.run.PythonScriptExecution
import com.jetbrains.python.run.target.HelpersAwareTargetEnvironmentRequest
import com.starnotesxj.sageide.SageBundle
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path

/**
 * Python debugger-compatible state for a native Sage launch.
 *
 * Sage source is loaded with the standard Sage command-line prelude and
 * file-level preparser before it is executed. The generated code keeps the
 * original .sage path as its filename, so pydevd can map frames and
 * breakpoints to the editor's source instead of the temporary launcher.
 *
 * PyDebugRunner uses the Python Target API: its target and interpreter come
 * from the Python SDK selected on this run configuration. The separate Sage
 * Runtime SDK is not a Python SDK and cannot select that target. WSL debugging
 * therefore requires a Python SDK for the same Conda Sage environment. The
 * legacy GeneralCommandLine path below retains the Sage runtime wrapper, but is
 * not the interpreter-selection path used by PyDebugRunner. Docker and SSH
 * debugger helper deployment and path/port mapping remain unsupported.
 */
class SageDebugCommandLineState(
    private val configuration: SageRunConfiguration,
    environment: ExecutionEnvironment,
) : PythonCommandLineState(configuration, environment) {

    private var launcherPath: Path? = null

    /** PyDebugRunner uses PythonCommandLineState's Target API, not generateCommandLine(). */
    override fun buildPythonExecution(request: HelpersAwareTargetEnvironmentRequest): PythonExecution {
        val sdk = getSdk()
        if (sdk?.sdkType !== PythonSdkType.getInstance()) {
            throw ExecutionException(SageBundle.message("run.debug.python.sdk.required"))
        }
        val script = Path.of(configuration.scriptPath).toAbsolutePath().normalize()
        val launcher = launcherPath ?: createLauncher(script).also { launcherPath = it }
        val targetRequest = request.targetEnvironmentRequest
        val settings = SageRunSettings.getInstance().getState()
        val plan = createSageDebugExecutionPlan(
            launcher = launcher,
            script = script,
            scriptParameters = tokenizeArguments(configuration.sageScriptParameters),
            interpreterParameters = tokenizeArguments(settings.sageParameters),
        )
        configuration.clearDebugLaunchContext(this)
        return PythonScriptExecution().apply {
            pythonScriptPath = getTargetPath(targetRequest, plan.launcher)
            addParameter(getTargetPath(targetRequest, plan.script))
            addParameters(plan.scriptParameters)
            additionalInterpreterParameters.addAll(plan.interpreterParameters)
            charset = EncodingProjectManager.getInstance(configuration.project).defaultCharset
        }
    }

    override fun generateCommandLine(): GeneralCommandLine {
        val settings = SageRunSettings.getInstance().getState()
        val script = Path.of(configuration.scriptPath).toAbsolutePath().normalize()
        val launcher = launcherPath ?: createLauncher(script).also { launcherPath = it }
        val usesConfiguredWsl = configuration.usesConfiguredWslRuntime(settings)
        val executableResolution = if (usesConfiguredWsl) null else configuration.resolveSageExecutables()
        if (executableResolution != null && !executableResolution.succeeded) {
            throw ExecutionException(
                executableResolution.diagnostics.firstOrNull()?.message
                    ?: "The selected SageMath runtime has no usable bundled Python interpreter",
            )
        }
        val executables = executableResolution?.value
        val mode = if (usesConfiguredWsl) {
            ExecutionMode.WSL
        } else {
            when (executables!!.target) {
                com.starnotesxj.sagemath.runtime.RuntimeTarget.Native -> ExecutionMode.NATIVE
                is com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl -> ExecutionMode.WSL
                is com.starnotesxj.sagemath.runtime.RuntimeTarget.Docker ->
                    throw ExecutionException("Container Sage debugging is unavailable: helper deployment, source mapping, and debug-port transport are not validated")
                is com.starnotesxj.sagemath.runtime.RuntimeTarget.RemoteSsh ->
                    throw ExecutionException("SSH SageMath debugging is not supported: verified remote debugger, helper deployment, port forwarding, and source mapping are required")
            }
        }
        val commandLine = if (mode == ExecutionMode.WSL) {
            val command = if (usesConfiguredWsl) {
                wslConfiguredDebugScript(
                    pythonExecutable = settings.wslPythonExecutable.trim().takeIf { it.isNotEmpty() }
                        ?: throw ExecutionException("WSL Sage Python was not discovered; run Sage discovery before debugging"),
                    environment = settings.wslCondaEnvironment,
                    condaExecutable = settings.wslCondaExecutable,
                )
            } else {
                val resolvedExecutables = executables!!
                val bundledPython = resolvedExecutables.python
                    ?: throw ExecutionException("The verified SageMath runtime has no usable bundled Python interpreter")
                wslDebugScript(settings.wslCondaEnvironment, resolvedExecutables.sage, bundledPython, settings.wslCondaExecutable)
            }
            GeneralCommandLine(
                "wsl.exe", "-d", settings.wslDistribution, "--exec", "/bin/bash", "-lc",
                command,
                // bash -c uses the next item as $0; the debugger's injected
                // arguments follow it and are forwarded by the WSL wrapper.
                "sage-debug-entry",
            )
        } else {
            val pythonExecutable = executables!!.python
                ?: throw ExecutionException("The verified SageMath runtime has no usable bundled Python interpreter")
            GeneralCommandLine(pythonExecutable)
                .withWorkDirectory(script.parent?.toString())
        }
        createStandardGroups(commandLine)

        val executableOptions = commandLine.parametersList.getParamsGroup(EXE_OPTIONS)
            ?: ParamsGroup(EXE_OPTIONS)
        executableOptions.addParameters(tokenizeArguments(settings.sageParameters))

        // PyDebugRunner adds pydevd and --file to the Debugger group.  The
        // launcher is therefore the first Script-group argument consumed by
        // pydevd's --file option; the .sage path and user args reach the
        // launcher as sys.argv[1..].
        val scriptGroup = commandLine.parametersList.getParamsGroup(SCRIPT)
            ?: ParamsGroup(SCRIPT)
        scriptGroup.addParameter(launcher.toString())
        scriptGroup.addParameter(script.toString())
        scriptGroup.addParameters(tokenizeArguments(configuration.sageScriptParameters))
        configuration.clearDebugLaunchContext(this)
        return commandLine
    }

    internal fun debugpyScriptName(): String = launcherForExecution().toString()

    internal fun debugpyScriptParameters(): String {
        val script = Path.of(configuration.scriptPath).toAbsolutePath().normalize()
        return formatSageDebugpyScriptParameters(script, tokenizeArguments(configuration.sageScriptParameters))
    }

    internal fun debugpyInterpreterArguments(): List<String> =
        tokenizeArguments(SageRunSettings.getInstance().getState().sageParameters)

    private fun launcherForExecution(): Path =
        launcherPath ?: createLauncher(Path.of(configuration.scriptPath).toAbsolutePath().normalize())
            .also { launcherPath = it }

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
            import tokenize
            from sage.repl.preparse import preparse_file

            target = pathlib.Path(sys.argv[1]).resolve()
            with tokenize.open(target) as source_file:
                source = source_file.read()
            sys.argv = [str(target), *sys.argv[2:]]
            namespace = {
                "__name__": "__main__",
                "__file__": str(target),
                "__package__": None,
            }
            # Match the prelude Sage adds when it runs a .sage script directly.
            exec("from sage.all_cmdline import *", namespace, namespace)
            code = compile(preparse_file(source, namespace), str(target), "exec")
            exec(code, namespace, namespace)
        """.trimIndent()
    }
}

internal data class SageDebugExecutionPlan(
    val launcher: Path,
    val script: Path,
    val scriptParameters: List<String>,
    val interpreterParameters: List<String>,
)

internal fun createSageDebugExecutionPlan(
    launcher: Path,
    script: Path,
    scriptParameters: List<String>,
    interpreterParameters: List<String>,
): SageDebugExecutionPlan = SageDebugExecutionPlan(launcher, script, scriptParameters, interpreterParameters)

internal fun formatSageDebugpyScriptParameters(script: Path, arguments: List<String>): String =
    com.intellij.util.execution.ParametersListUtil.join(listOf(script.toString()) + arguments)

/** Shell-style argument parsing shared by Sage run/debug command builders. */
internal fun tokenizeArguments(value: String): List<String> =
    com.intellij.util.execution.ParametersListUtil.parse(value)
