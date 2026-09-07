package com.starnotesxj.sageide.run

import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.ProcessOutput
import com.intellij.execution.util.ExecUtil
import java.util.concurrent.ConcurrentHashMap

/**
 * Best-effort detection of Sage installations for each execution mode.
 * Detected paths are used to pre-fill the settings; when nothing is found
 * the user fills the fields manually.
 */
data class WslSageRuntime(
    val distribution: String,
    val condaEnvironment: String,
    val condaExecutable: String?,
    val sageExecutable: String,
    val pythonExecutable: String?,
    val version: String?,
)

data class DetectedSageRuntimes(
    val nativeExecutable: String?,
    val wslRuntimes: List<WslSageRuntime>,
)

object SageAutoDetect {

    /**
     * Performs the one-time, best-effort discovery used after the plugin starts.
     * This may start WSL and must therefore run on a background executor.
     */
    fun detectInstalledRuntimes(timeoutMillis: Long = 10_000): DetectedSageRuntimes {
        require(timeoutMillis > 0) { "Runtime discovery timeout must be positive" }
        return DetectedSageRuntimes(
            nativeExecutable = detectNativeSage(timeoutMillis),
            wslRuntimes = detectWslRuntimes(timeoutMillis),
        )
    }

    fun detectWslRuntimes(timeoutMillis: Long = 10_000): List<WslSageRuntime> {
        require(timeoutMillis > 0) { "WSL discovery timeout must be positive" }
        return listWslDistributions(timeoutMillis)
            .asSequence()
            .filterNot { it.startsWith("docker-desktop", ignoreCase = true) }
            .mapNotNull { distribution ->
                detectWslRuntime(
                    distribution = distribution,
                    condaEnvironment = "sage",
                    condaExecutable = "",
                    sageExecutable = "",
                    timeoutMillis = timeoutMillis,
                )
            }
            .toList()
    }

    /**
     * Detects the actual WSL environment through an explicit bash executable.
     * `wsl.exe --exec` is intentional: the distribution's default shell may be
     * zsh, while conda's `shell.bash hook` must be evaluated by bash.
     */
    fun detectWslRuntime(
        distribution: String,
        condaEnvironment: String,
        condaExecutable: String,
        sageExecutable: String,
        timeoutMillis: Long = 60_000,
    ): WslSageRuntime? {
        require(distribution.isNotBlank()) { "WSL distribution must not be blank" }
        require(condaEnvironment.isNotBlank()) { "WSL Conda environment must not be blank" }
        validateWslPath(condaExecutable, "Conda executable")
        validateWslPath(sageExecutable, "Sage executable")
        val output = exec(
            GeneralCommandLine(
                "wsl.exe", "-d", distribution, "--exec", "/bin/bash", "-lc",
                wslProbeScript(condaEnvironment, condaExecutable, sageExecutable),
            ),
            timeoutMillis,
        ) ?: return null
        if (output.exitCode != 0 || output.isTimeout) return null
        val values = output.stdout.replace("\u0000", "").lineSequence()
            .mapNotNull { line -> line.split('=', limit = 2).takeIf { it.size == 2 } }
            .associate { it[0].trim() to it[1].trim() }
        val sage = values["SAGE"]?.takeIf { it.isNotBlank() } ?: return null
        return WslSageRuntime(
            distribution = distribution.trim(),
            condaEnvironment = condaEnvironment.trim().ifBlank { "sage" },
            condaExecutable = values["CONDA"]?.takeIf { it.isNotBlank() },
            sageExecutable = sage,
            pythonExecutable = values["PYTHON"]?.takeIf { it.isNotBlank() },
            version = values["VERSION"]?.takeIf { it.isNotBlank() },
        )
    }

    fun detectWslSage(distribution: String): String? =
        detectWslRuntime(distribution, "sage", "", "")?.sageExecutable

    fun probeWslScript(
        condaEnvironment: String = "sage",
        condaExecutable: String = "",
        sageExecutable: String = "",
    ): String = wslProbeScript(condaEnvironment, condaExecutable, sageExecutable)

    private fun wslProbeScript(environment: String, configuredConda: String, configuredSage: String): String = buildString {
        appendLine("set +e")
        appendLine("if [ -f \"${'$'}HOME/.bashrc\" ]; then . \"${'$'}HOME/.bashrc\" >/dev/null 2>&1 || true; fi")
        val conda = configuredConda.trim().takeIf { it.isNotEmpty() }
        if (configuredSage.trim().isEmpty()) {
            if (conda != null) {
                appendLine("conda_executable=${shellQuote(conda)}")
                appendLine("[ -x \"${'$'}conda_executable\" ] || exit 127")
                appendLine("eval \"${'$'}(\"${'$'}conda_executable\" shell.bash hook)\"")
            }
            else {
                appendLine("for conda_sh in \\")
                appendLine("    \"${'$'}HOME/miniconda3/etc/profile.d/conda.sh\" \\")
                appendLine("    \"${'$'}HOME/anaconda3/etc/profile.d/conda.sh\" \\")
                appendLine("    \"${'$'}HOME/mambaforge/etc/profile.d/conda.sh\" \\")
                appendLine("    \"${'$'}HOME/miniforge3/etc/profile.d/conda.sh\" \\")
                appendLine("    \"/opt/conda/etc/profile.d/conda.sh\"; do")
                appendLine("    if [ -f \"${'$'}conda_sh\" ]; then . \"${'$'}conda_sh\"; conda_executable=\"${'$'}{conda_sh%/etc/profile.d/conda.sh}/bin/conda\"; break; fi")
                appendLine("done")
                appendLine("if ! type conda >/dev/null 2>&1; then")
                appendLine("    for conda_executable in \\")
                appendLine("        \"${'$'}HOME/miniconda3/bin/conda\" \\")
                appendLine("        \"${'$'}HOME/anaconda3/bin/conda\" \\")
                appendLine("        \"${'$'}HOME/mambaforge/bin/conda\" \\")
                appendLine("        \"${'$'}HOME/miniforge3/bin/conda\" \\")
                appendLine("        \"/opt/conda/bin/conda\"; do")
                appendLine("        if [ -x \"${'$'}conda_executable\" ]; then eval \"${'$'}(\"${'$'}conda_executable\" shell.bash hook)\"; break; fi")
                appendLine("    done")
                appendLine("fi")
            }
            appendLine("if type conda >/dev/null 2>&1; then conda activate ${shellQuote(environment.trim().ifBlank { "sage" })} >/dev/null 2>&1; fi")
        }
        appendLine("sage_executable=${shellQuote(configuredSage.trim())}")
        if (configuredSage.trim().isEmpty()) {
            appendLine("sage_executable=\"${'$'}(command -v sage || true)\"")
        }
        val configuredPython = configuredSage.trim()
            .takeIf { it.isNotEmpty() }
            ?.substringBeforeLast('/', "")
            ?.takeIf { it.isNotEmpty() }
            ?.let { "$it/python" }
        if (configuredPython != null) {
            appendLine("python_executable=${shellQuote(configuredPython)}")
            appendLine("if [ ! -x \"${'$'}python_executable\" ]; then python_executable=\"${'$'}(command -v python || command -v python3 || true)\"; fi")
        }
        else {
            appendLine("python_executable=\"${'$'}(command -v python || command -v python3 || true)\"")
        }
        appendLine("[ -n \"${'$'}sage_executable\" ] && [ -x \"${'$'}sage_executable\" ] || exit 127")
        appendLine("printf 'CONDA=%s\\n' \"${'$'}{conda_executable:-}\"")
        appendLine("printf 'SAGE=%s\\n' \"${'$'}sage_executable\"")
        appendLine("printf 'PYTHON=%s\\n' \"${'$'}python_executable\"")
        appendLine("printf 'VERSION=%s\\n' \"${'$'}(\"${'$'}sage_executable\" --version 2>/dev/null || true)\"")
    }

    fun detectNativeSage(timeoutMillis: Long = 10_000): String? {
        val output = exec(GeneralCommandLine("where", "sage"), timeoutMillis) ?: return null
        return output.stdout.replace("\u0000", "").trim().lines().firstOrNull()?.takeIf { it.isNotBlank() }
    }

    internal fun listWslDistributions(timeoutMillis: Long = 10_000): List<String> {
        val output = exec(GeneralCommandLine("wsl.exe", "--list", "--quiet"), timeoutMillis)
            ?: return emptyList()
        return parseWslDistributions(output.stdout)
    }

    internal fun parseWslDistributions(output: String): List<String> = output
        // `wsl.exe --list` can emit UTF-16LE bytes through a process API that
        // decoded them as UTF-8, leaving NUL characters between ASCII letters.
        .replace("\u0000", "")
        .lineSequence()
        .map { it.trim().trimStart('*').trim().removePrefix("\uFEFF") }
        .filter { it.isNotBlank() }
        .distinct()
        .toList()

    fun detectDockerImage(): String? {
        val output = exec(GeneralCommandLine("docker", "images", "--format", "{{.Repository}}")) ?: return null
        return output.stdout.trim().lines()
            .firstOrNull { it.contains("sage", ignoreCase = true) }
            ?.takeIf { it.isNotBlank() }
    }

    fun validateConfiguredWslSettings(
        distribution: String,
        condaEnvironment: String,
        condaExecutable: String,
        sageExecutable: String,
        pythonExecutable: String = "",
    ) {
        require(distribution.isNotBlank()) { "WSL distribution must not be blank" }
        require(condaEnvironment.isNotBlank()) { "WSL Conda environment must not be blank" }
        validateWslPath(condaExecutable, "Conda executable")
        validateWslPath(sageExecutable, "Sage executable")
        validateWslPath(pythonExecutable, "Python executable")
    }

    private fun validateWslPath(value: String, label: String) {
        val trimmed = value.trim()
        if (trimmed.isEmpty()) return
        require(trimmed.startsWith("/") && !trimmed.startsWith("//")) { "$label must be an absolute POSIX path" }
        require(trimmed.none(Char::isISOControl) && '\\' !in trimmed) { "$label must use printable POSIX path characters" }
    }

    private fun exec(commandLine: GeneralCommandLine, timeoutMillis: Long = 10_000): ProcessOutput? {
        return try {
            ExecUtil.execAndGetOutput(commandLine, timeoutMillis.coerceIn(1, Int.MAX_VALUE.toLong()).toInt())
        }
        catch (_: Exception) {
            null
        }
    }
}

/**
 * Resolves `$HOME` inside a WSL distribution so `~/...` paths in the
 * settings can be expanded on the plugin side (wsl.exe does not expand `~`
 * in the `--`-separated command).
 */
object WslHomeResolver {
    private val cache = ConcurrentHashMap<String, String>()

    fun resolve(distribution: String): String? {
        cache[distribution]?.let { return it }
        val output = try {
            // wsl.exe cold start can take well over ten seconds.
            ExecUtil.execAndGetOutput(
                GeneralCommandLine("wsl.exe", "-d", distribution, "--exec", "/bin/bash", "-lc", "printf '%s\\n' \$HOME"),
                60_000,
            )
        }
        catch (_: Exception) {
            return null
        }
        if (output.exitCode != 0 || output.isTimeout) return null
        val home = output.stdout.trim().lines().lastOrNull()?.trim()
        if (!home.isNullOrBlank()) {
            cache[distribution] = home
        }
        return home
    }

    /** Expands a leading `~` using the WSL distribution's home directory. */
    fun expand(distribution: String, path: String): String {
        if (!path.startsWith("~/")) return path
        val home = resolve(distribution) ?: return path
        return home + path.removePrefix("~")
    }
}
