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

/** Debug wrapper for settings-backed WSL Sage with an already discovered Python path. */
internal fun wslConfiguredDebugScript(pythonExecutable: String): String = """
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
    python_executable=${shellQuote(pythonExecutable.trim().takeIf { it.isNotEmpty() } ?: error("A discovered WSL Python path is required for debugging"))}
    [ -x "${'$'}python_executable" ] || { echo "Sage IDE Support: discovered Python was not found in WSL" >&2; exit 127; }
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
