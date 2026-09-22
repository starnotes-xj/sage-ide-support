package com.starnotesxj.sageide.inline

import kotlinx.coroutines.withTimeoutOrNull
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds

/**
 * Async boundary between Sage's exact member filter and a scorer.
 *
 * The current implementation is an in-process semantic scorer. Keeping the
 * boundary suspendable makes a persistent local native server an additive
 * implementation detail rather than part of the typing/PSI path.
 */
internal fun interface SageInlineScoringBackend {
    suspend fun predict(request: SageInlineScoringRequest): SageInlinePrediction?
}

/** The zero-process default used until a native model is installed and verified. */
internal object SageInlineSemanticScoringBackend : SageInlineScoringBackend {
    override suspend fun predict(request: SageInlineScoringRequest): SageInlinePrediction? =
        SageInlineSemanticModel.predict(request)
}

/**
 * Narrow protocol implemented by a persistent local native scorer.
 *
 * It returns a candidate name, never source text. The plugin validates that
 * name against [SageInlineScoringRequest.candidates] before rendering it, so a
 * timeout, crashed server, stale response, or malformed output is harmless.
 */
internal fun interface SageInlineNativeScorer {
    suspend fun chooseCandidate(request: SageInlineScoringRequest): String?
}

/**
 * Deadline-protected adapter for a future native server.
 *
 * This adapter intentionally has no process-start side effect. Starting a
 * server while the user types would recreate the latency this feature is meant
 * to avoid; lifecycle ownership and binary/model installation must be handled
 * separately before this backend is selected.
 */
internal class SageNativeInlineScoringBackend(
    private val nativeScorer: SageInlineNativeScorer,
    private val fallback: SageInlineScoringBackend = SageInlineSemanticScoringBackend,
    private val deadline: Duration = NATIVE_SCORING_DEADLINE,
) : SageInlineScoringBackend {
    override suspend fun predict(request: SageInlineScoringRequest): SageInlinePrediction? {
        val selectedName = withTimeoutOrNull(deadline) {
            nativeScorer.chooseCandidate(request)
        }
        val candidate = request.candidates.singleOrNull { it.name == selectedName }
        if (candidate != null) {
            val suffix = candidate.name.removePrefix(request.prefix)
            if (suffix.isNotEmpty()) {
                return SageInlinePrediction(suffix + if (candidate.callable) "()" else "")
            }
        }
        return fallback.predict(request)
    }

    private companion object {
        // This is asynchronous and never holds PSI or the EDT. Thirty
        // milliseconds accommodates a busy coroutine/IO dispatcher while
        // remaining well below the visible 220ms editor debounce interval.
        val NATIVE_SCORING_DEADLINE: Duration = 30.milliseconds
    }
}
