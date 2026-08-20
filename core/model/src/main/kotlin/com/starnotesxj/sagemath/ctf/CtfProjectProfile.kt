package com.starnotesxj.sagemath.ctf

import com.starnotesxj.sagemath.ctf.model.ExecutionTarget

/**
 * Reproducible execution settings for one CTF challenge or experiment.
 */
data class CtfProjectProfile(
    val name: String,
    val flagPattern: String = "flag\\{[^\\r\\n}]+}",
    val executionTarget: ExecutionTarget = ExecutionTarget.Native,
    val workingDirectory: String? = null,
    val standardInput: String? = null,
    val arguments: List<String> = emptyList(),
    val environment: Map<String, String> = emptyMap(),
    val timeoutMillis: Long = DEFAULT_TIMEOUT_MILLIS,
    val maxOutputBytes: Long = DEFAULT_MAX_OUTPUT_BYTES,
) {
    init {
        require(name.isNotBlank()) { "CTF profile name must not be blank" }
        require(flagPattern.isNotBlank()) { "Flag pattern must not be blank" }
        require(timeoutMillis > 0) { "Timeout must be positive" }
        require(maxOutputBytes > 0) { "Maximum output size must be positive" }
    }

    companion object {
        const val DEFAULT_TIMEOUT_MILLIS = 30_000L
        const val DEFAULT_MAX_OUTPUT_BYTES = 1_048_576L
    }
}
