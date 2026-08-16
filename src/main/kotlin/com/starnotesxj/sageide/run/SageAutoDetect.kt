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
object SageAutoDetect {

    private const val WSL_PROBE = (
        """for p in "${'$'}HOME/miniconda3/envs/sage/bin/sage" "${'$'}HOME/anaconda3/envs/sage/bin/sage" """ +
        """"${'$'}HOME/mambaforge/envs/sage/bin/sage" "/usr/bin/sage" "/usr/local/bin/sage"; do """ +
        """[ -x "${'$'}p" ] && echo "${'$'}p" && break; done"""
        )

    fun detectWslSage(distribution: String): String? {
        val output = exec(GeneralCommandLine("wsl.exe", "-d", distribution, "--", "bash", "-lc", WSL_PROBE))
            ?: return null
        return output.stdout.trim().lines().firstOrNull()?.takeIf { it.isNotBlank() }
    }

    fun detectNativeSage(): String? {
        val output = exec(GeneralCommandLine("where", "sage")) ?: return null
        return output.stdout.trim().lines().firstOrNull()?.takeIf { it.isNotBlank() }
    }

    fun detectDockerImage(): String? {
        val output = exec(GeneralCommandLine("docker", "images", "--format", "{{.Repository}}")) ?: return null
        return output.stdout.trim().lines()
            .firstOrNull { it.contains("sage", ignoreCase = true) }
            ?.takeIf { it.isNotBlank() }
    }

    private fun exec(commandLine: GeneralCommandLine): ProcessOutput? {
        return try {
            ExecUtil.execAndGetOutput(commandLine, 10_000)
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
                GeneralCommandLine("wsl.exe", "-d", distribution, "--", "bash", "-lc", "echo \$HOME"),
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
