package com.starnotesxj.sageide.run

/** Converts a Windows path to the path exposed by WSL's DrvFs mount. */
internal fun toWslPath(windowsPath: String): String {
    val normalized = windowsPath.replace('\\', '/')
    val match = Regex("^([A-Za-z]):/(.*)$").matchEntire(normalized) ?: return normalized
    return "/mnt/${match.groupValues[1].lowercase()}/${match.groupValues[2]}"
}

/** Quotes one argument for a POSIX shell without allowing shell expansion. */
internal fun shellQuote(value: String): String = "'${value.replace("'", "'\\''")}'"

internal fun wslCondaPrelude(environment: String, condaExecutable: String? = null): String = buildString {
    appendLine("set -e")
    appendLine("if [ -f \"${'$'}HOME/.bashrc\" ]; then . \"${'$'}HOME/.bashrc\" >/dev/null 2>&1 || true; fi")
    val configuredConda = condaExecutable?.trim()?.takeIf { it.isNotEmpty() }
    if (configuredConda != null) {
        appendLine("conda_executable=${shellQuote(configuredConda)}")
        appendLine("if [ ! -x \"${'$'}conda_executable\" ]; then echo \"Sage IDE Support: configured conda executable was not found in WSL\" >&2; exit 127; fi")
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
    appendLine("if ! type conda >/dev/null 2>&1; then echo \"Sage IDE Support: conda was not found in WSL\" >&2; exit 127; fi")
    append("conda activate ")
    append(shellQuote(environment.ifBlank { "sage" }))
}

internal fun wslRunScript(
    environment: String,
    executable: String,
    arguments: List<String>,
    condaExecutable: String? = null,
): String = buildString {
    appendLine(wslCondaPrelude(environment, condaExecutable))
    append("exec ")
    append(shellQuote(executable))
    arguments.forEach { append(' ').append(shellQuote(it)) }
}

/** Returns the direct WSL command arguments shown by IntelliJ's run console. */
internal fun wslDirectRunArguments(
    distribution: String,
    executable: String,
    arguments: List<String>,
): List<String> = listOf("-d", distribution, "--", executable) + arguments

/** Uses the new WSL field first and keeps the legacy saved setting compatible. */
internal fun configuredWslSageExecutable(settings: SageRunSettings.State): String? =
    settings.wslSageExecutable.trim().takeIf { it.isNotEmpty() }
        ?: settings.sageExecutable.trim().takeIf { it.startsWith("/") }

/**
 * Run wrapper for an externally managed WSL Conda installation. The host must not
 * discover the Sage executable before starting this command: IntelliJ may call
 * the command-state factory on the EDT. The activated shell resolves `sage` in
 * the target environment instead.
 */
internal fun wslConfiguredRunScript(
    environment: String,
    configuredExecutable: String,
    arguments: List<String>,
    condaExecutable: String? = null,
): String = buildString {
    // Keep the command shown in the run console readable.  The old fallback
    // embedded the full multi-path Conda discovery script here, which made a
    // normal Sage run look like a probe and obscured the actual script launch.
    // An explicit executable still bypasses the shell entirely in
    // SageCommandLineState; this branch is only for settings with no path.
    val executable = configuredExecutable.trim()
    if (executable.isNotEmpty()) {
        append("exec ").append(shellQuote(executable))
    }
    else {
        val configuredConda = condaExecutable?.trim()?.takeIf { it.isNotEmpty() }
        if (configuredConda != null) {
            append("eval \"${'$'}(")
                .append(shellQuote(configuredConda))
                .append(" shell.bash hook)\" && ")
        }
        else {
            // The SageMath Conda layout is deterministic for the default
            // WSL installation.  Source that one hook first; only fall back
            // to the user's shell profile when it is absent.  This keeps the
            // displayed command to one short launch expression and avoids the
            // old multi-path discovery loop.
            append("if [ -f \"${'$'}HOME/miniconda3/etc/profile.d/conda.sh\" ]; then . \"${'$'}HOME/miniconda3/etc/profile.d/conda.sh\"; elif [ -f \"${'$'}HOME/.bashrc\" ]; then . \"${'$'}HOME/.bashrc\" >/dev/null 2>&1 || true; fi; ")
        }
        append("conda activate ")
            .append(shellQuote(environment.ifBlank { "sage" }))
            .append(" >/dev/null 2>&1 && exec sage")
    }
    arguments.forEach { append(' ').append(shellQuote(it)) }
}

/**
 * Shell wrapper used by the native PyCharm debugger patcher in WSL mode.
 * PyDebugRunner appends its pydevd arguments to the command line.  `bash -lc`
 * exposes those arguments as `$0`/`$@`; this wrapper activates conda, converts
 * Windows paths such as the PyCharm helper path to /mnt/<drive>/..., and then
 * forwards every argument to the Sage Python entry point.
 */
/** Debug wrapper for settings-backed WSL Sage. The child resolves `sage` and
 * uses its interpreter after Conda activation; no host-side runtime probe is needed. */
internal fun wslConfiguredDebugScript(
    environment: String,
    condaExecutable: String? = null,
): String = """
    ${wslCondaPrelude(environment, condaExecutable)}
    map_arg() {
        case "${'$'}1" in
            [A-Za-z]:[\\/]* )
                local drive="${'$'}{1:0:1}"
                local rest="${'$'}{1:2}"
                rest="${'$'}{rest//\\\\//}"
                printf '/mnt/%s/%s' "${'$'}{drive,,}" "${'$'}rest"
                ;;
            * ) printf '%s' "${'$'}1" ;;
        esac
    }
    host_ip="${'$'}(awk '/^nameserver / { print ${'$'}2; exit }' /etc/resolv.conf)"
    args=()
    previous=""
    for raw_arg in "${'$'}@"; do
        arg="${'$'}(map_arg "${'$'}raw_arg")"
        if [ "${'$'}previous" = "--client" ] && [ "${'$'}arg" = "127.0.0.1" ] && [ -n "${'$'}host_ip" ]; then
            arg="${'$'}host_ip"
        fi
        args+=("${'$'}arg")
        previous="${'$'}arg"
    done
    sage_executable="${'$'}(command -v sage || true)"
    [ -n "${'$'}sage_executable" ] || { echo "Sage IDE Support: sage was not found in WSL" >&2; exit 127; }
    python_executable="${'$'}(command -v python || true)"
    [ -n "${'$'}python_executable" ] || { echo "Sage IDE Support: python was not found in the activated WSL environment" >&2; exit 127; }
    exec "${'$'}python_executable" "${'$'}{args[@]}"
""".trimIndent()

internal fun wslDebugScript(
    environment: String,
    executable: String,
    pythonExecutable: String? = null,
    condaExecutable: String? = null,
): String = """
    ${wslCondaPrelude(environment, condaExecutable)}
    map_arg() {
        case "$1" in
            [A-Za-z]:[\\/]* )
                local drive="${'$'}{1:0:1}"
                local rest="${'$'}{1:2}"
                rest="${'$'}{rest//\\\\//}"
                printf '/mnt/%s/%s' "${'$'}{drive,,}" "${'$'}rest"
                ;;
            * ) printf '%s' "$1" ;;
        esac
    }
    # In WSL2, 127.0.0.1 is the Linux VM.  The IDE's debug server is on the
    # Windows host, whose gateway address is exposed as the resolv.conf DNS.
    host_ip="${'$'}(awk '/^nameserver / { print ${'$'}2; exit }' /etc/resolv.conf)"
    args=()
    previous=""
    for raw_arg in "${'$'}@"; do
        arg="${'$'}(map_arg "${'$'}raw_arg")"
        if [ "${'$'}previous" = "--client" ] && [ "${'$'}arg" = "127.0.0.1" ] && [ -n "${'$'}host_ip" ]; then
            arg="${'$'}host_ip"
        fi
        args+=("${'$'}arg")
        previous="${'$'}arg"
    done
    python_executable=${shellQuote(pythonExecutable ?: error("A verified bundled SageMath Python path is required for debugging"))}
    exec "${'$'}python_executable" "${'$'}{args[@]}"
""".trimIndent()
