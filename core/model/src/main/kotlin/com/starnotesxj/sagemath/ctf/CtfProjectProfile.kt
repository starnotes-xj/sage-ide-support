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
    /**
     * Maximum execution time in milliseconds.
     *
     * `null` means no automatic deadline. A user cancellation must still be
     * honoured by the execution adapter. A positive value enables a deadline;
     * zero and negative values are invalid rather than overloaded sentinels.
     */
    val timeoutMillis: Long? = DEFAULT_TIMEOUT_MILLIS,
    val maxOutputBytes: Long = DEFAULT_MAX_OUTPUT_BYTES,
) {
    init {
        require(name.isNotBlank()) { "CTF profile name must not be blank" }
        require(flagPattern.isNotBlank()) { "Flag pattern must not be blank" }
        require(timeoutMillis == null || timeoutMillis > 0) {
            "Timeout must be null (unlimited) or positive"
        }
        require(maxOutputBytes > 0) { "Maximum output size must be positive" }
    }

    companion object {
        /** The product default is unlimited; explicit cancellation remains available. */
        val DEFAULT_TIMEOUT_MILLIS: Long? = null
        const val DEFAULT_MAX_OUTPUT_BYTES = 1_048_576L
    }
}
