package com.starnotesxj.sagemath.ctf

/** Structured result shared by Sage runs and future CTF tool adapters. */
data class ExecutionResult(
    val exitCode: Int?,
    val standardOutput: String,
    val standardError: String,
    val durationMillis: Long,
    val timedOut: Boolean = false,
    val outputTruncated: Boolean = false,
    val flags: List<String> = emptyList(),
)
