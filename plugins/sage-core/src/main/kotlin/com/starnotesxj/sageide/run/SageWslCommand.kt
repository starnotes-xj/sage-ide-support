package com.starnotesxj.sageide.run

/** Converts a Windows path to the path exposed by WSL's DrvFs mount. */
internal fun toWslPath(windowsPath: String): String {
    val normalized = windowsPath.replace('\\', '/')
    val match = Regex("^([A-Za-z]):/(.*)$").matchEntire(normalized) ?: return normalized
    return "/mnt/${match.groupValues[1].lowercase()}/${match.groupValues[2]}"
}

/** Quotes one argument for a POSIX shell without allowing shell expansion. */
internal fun shellQuote(value: String): String = "'${value.replace("'", "'\\''")}'"

internal fun wslCondaPrelude(environment: String): String = """
    set -e
    if [ -f "${'$'}HOME/.bashrc" ]; then . "${'$'}HOME/.bashrc" >/dev/null 2>&1 || true; fi
    for conda_sh in \
        "${'$'}HOME/miniconda3/etc/profile.d/conda.sh" \
        "${'$'}HOME/anaconda3/etc/profile.d/conda.sh" \
        "${'$'}HOME/mambaforge/etc/profile.d/conda.sh" \
        "${'$'}HOME/miniforge3/etc/profile.d/conda.sh" \
        "/opt/conda/etc/profile.d/conda.sh"; do
        if [ -f "${'$'}conda_sh" ]; then . "${'$'}conda_sh"; break; fi
    done
    if ! type conda >/dev/null 2>&1; then
        echo "Sage IDE Support: conda was not found in WSL" >&2
        exit 127
    fi
    conda activate ${shellQuote(environment.ifBlank { "sage" })}
""".trimIndent()

internal fun wslRunScript(
    environment: String,
    executable: String,
    arguments: List<String>,
): String = buildString {
    appendLine(wslCondaPrelude(environment))
    append("exec ")
    append(shellQuote(executable))
    arguments.forEach { append(' ').append(shellQuote(it)) }
}

/**
 * Shell wrapper used by the native PyCharm debugger patcher in WSL mode.
 * PyDebugRunner appends its pydevd arguments to the command line.  `bash -lc`
 * exposes those arguments as `$0`/`$@`; this wrapper activates conda, converts
 * Windows paths such as the PyCharm helper path to /mnt/<drive>/..., and then
 * forwards every argument to the Sage Python entry point.
 */
internal fun wslDebugScript(environment: String, executable: String): String = """
    ${wslCondaPrelude(environment)}
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
    python_executable=${shellQuote(executable)}
    case "${'$'}python_executable" in
        */sage) python_executable="${'$'}{python_executable%/sage}/python" ;;
    esac
    exec "${'$'}python_executable" "${'$'}{args[@]}"
""".trimIndent()
