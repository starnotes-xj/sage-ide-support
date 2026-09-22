package com.starnotesxj.sageide.inline

import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiComment
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil
import com.starnotesxj.sageide.completion.SageApiIndexService
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.type.SageIndexedTypeResolver
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyStringLiteralExpression

/**
 * Bounded semantic backend for Sage inline completion.
 *
 * The predictor intentionally receives only exact contracts from the existing
 * Sage index/type layer. It has no WSL dependency, does not execute Sage, and
 * returns no text when a member name is ambiguous. That makes it a safe local
 * baseline for a future learned/native backend instead of a second source of
 * speculative type information.
 */
@Service(Service.Level.PROJECT)
class SageInlinePredictionService(private val project: Project) {
    private val candidatesCache = SageInlineLruCache<CandidateKey, List<SageInlineCandidate>>(MAX_CACHE_ENTRIES)

    /**
     * Captures a small, immutable scoring request from PSI and the Sage index.
     *
     * This must run under a read action, but scoring deliberately must not. A
     * future native backend can therefore wait for a bounded response without
     * holding a PSI read lock or retaining editor objects across a document
     * edit.
     */
    internal fun prepareScoringRequest(file: PsiFile, offset: Int): SageInlineScoringRequest? {
        if (!SageFileUtils.isSageFile(file)) return null
        if (offset <= 0 || file.textLength == 0) return null

        val probe = file.findElementAt((offset - 1).coerceAtMost(file.textLength - 1)) ?: return null
        if (isInsideStringOrComment(probe)) return null

        val reference = qualifiedReferenceAt(probe) ?: return null
        val qualifier = reference.qualifier ?: return null
        val prefix = reference.referencedName.orEmpty()
        if (prefix.length < MIN_MEMBER_PREFIX) return null

        val query = SageApiIndexService.getInstance().query() ?: return null
        val owners = SageIndexedTypeResolver.ownersForExpression(qualifier, query)
        if (owners.isEmpty()) return null

        val key = CandidateKey(owners.sorted().joinToString("\u001f"), prefix)
        val candidates = candidatesCache.getOrPut(key) {
            val unique = linkedMapOf<String, SageInlineCandidate>()
            owners.asSequence()
                .take(MAX_OWNER_BRANCHES)
                .flatMap { owner -> query.members(owner).asSequence().take(MAX_MEMBERS_PER_OWNER) }
                .forEach { entry ->
                    val name = entry.qualifiedName.substringAfterLast('.')
                    if (!name.startsWith(prefix)) return@forEach
                    unique.putIfAbsent(name, SageInlineCandidate(name, entry.kind == SageApiSymbolKind.METHOD))
                }
            unique.values.toList()
        }
        return SageInlineScoringRequest(
            prefix = prefix,
            candidates = candidates,
            memberContext = memberContext(file, offset),
        )
    }

    /** Sends only prior code-member observations to the scorer, never raw CTF source. */
    private fun memberContext(file: PsiFile, offset: Int): String {
        val document = PsiDocumentManager.getInstance(project).getDocument(file) ?: return ""
        val end = offset.coerceAtMost(document.textLength)
        val start = (end - MAX_LEFT_CONTEXT_CHARACTERS).coerceAtLeast(0)
        return MEMBER_OBSERVATION.findAll(document.immutableCharSequence.subSequence(start, end))
            .mapNotNull { match ->
                // Inspect the member identifier rather than the dot token. In
                // incomplete Python/Sage PSI the dot can be an error leaf,
                // whereas the identifier retains its string/comment ancestry.
                val matchOffset = start + match.range.first + 1
                val leaf = file.findElementAt(matchOffset) ?: return@mapNotNull null
                if (isInsideStringOrComment(leaf)) {
                    null
                } else {
                    ".${match.groupValues[1]}"
                }
            }
            .take(MAX_MEMBER_OBSERVATIONS)
            .joinToString("\n")
    }

    private fun qualifiedReferenceAt(probe: PsiElement): PyReferenceExpression? =
        sequenceOf(
            PsiTreeUtil.getParentOfType(probe, PyReferenceExpression::class.java),
            PsiTreeUtil.getParentOfType(PsiTreeUtil.prevVisibleLeaf(probe), PyReferenceExpression::class.java),
        ).filterNotNull().firstOrNull { it.isQualified }

    /** Handles both a token *inside* a non-code PSI node and the node itself. */
    private fun isInsideStringOrComment(element: PsiElement): Boolean =
        element is PsiComment ||
            element is PyStringLiteralExpression ||
            PsiTreeUtil.getParentOfType(element, PyStringLiteralExpression::class.java, false) != null ||
            PsiTreeUtil.getParentOfType(element, PsiComment::class.java, false) != null

    private data class CandidateKey(val owners: String, val prefix: String)

    companion object {
        private const val MIN_MEMBER_PREFIX = 2
        private const val MAX_CACHE_ENTRIES = 256
        private const val MAX_OWNER_BRANCHES = 4
        private const val MAX_MEMBERS_PER_OWNER = 512
        private const val MAX_LEFT_CONTEXT_CHARACTERS = 2 * 1024
        private const val MAX_MEMBER_OBSERVATIONS = 128
        private val MEMBER_OBSERVATION = Regex("""\.([A-Za-z_][A-Za-z0-9_]*)""")

        fun getInstance(project: Project): SageInlinePredictionService = project.service()
    }
}

/** A precise candidate passed to the local model/backend boundary. */
internal data class SageInlineCandidate(val name: String, val callable: Boolean)

/**
 * Immutable, type-filtered input for an inline scorer.
 *
 * A scorer may rank only [candidates]. It never receives a mutable PSI object,
 * a whole source file, or a Sage runtime handle, and therefore cannot invent a
 * member outside the receiver's concrete Sage type.
 */
internal data class SageInlineScoringRequest(
    val prefix: String,
    val candidates: List<SageInlineCandidate>,
    /** Bounded, redacted history of `.member` observations preceding the caret. */
    val memberContext: String = "",
)

/** Text inserted by the platform if the user accepts the inline continuation. */
internal data class SageInlinePrediction(val suffix: String)

/**
 * First local model: require one exact semantic continuation.
 *
 * It is deliberately conservative. A future native learned model may rank
 * several candidates through the same request/result boundary, but cannot
 * bypass this exact candidate filter or introduce names absent from the
 * receiver's proved concrete type.
 */
internal object SageInlineSemanticModel {
    fun predict(prefix: String, candidates: List<SageInlineCandidate>): SageInlinePrediction? {
        val candidate = candidates.singleOrNull() ?: return null
        return predictionFor(prefix, candidate)
    }

    /**
     * The zero-process fallback applies the same bounded confidence rule as
     * the native scorer.  A busy machine may miss the native deadline, but a
     * previously established, unambiguous local member pattern must not turn
     * into a silent no-result merely because a background process was late.
     */
    fun predict(request: SageInlineScoringRequest): SageInlinePrediction? {
        predict(request.prefix, request.candidates)?.let { return it }
        val byName = request.candidates.associateBy { it.name }
        val counts = request.memberContext
            .lineSequence()
            .map { it.removePrefix(".") }
            .filter(byName::containsKey)
            .groupingBy { it }
            .eachCount()
        val ranked = counts.entries.sortedWith(
            compareByDescending<Map.Entry<String, Int>> { it.value }.thenBy { it.key },
        )
        val winner = ranked.firstOrNull() ?: return null
        val runnerUpCount = ranked.getOrNull(1)?.value ?: 0
        if (winner.value < MIN_CONTEXT_OCCURRENCES || winner.value - runnerUpCount < MIN_CONTEXT_LEAD) return null
        return predictionFor(request.prefix, byName.getValue(winner.key))
    }

    private fun predictionFor(prefix: String, candidate: SageInlineCandidate): SageInlinePrediction? {
        val suffix = candidate.name.removePrefix(prefix)
        if (suffix.isEmpty()) return null
        return SageInlinePrediction(suffix + if (candidate.callable) "()" else "")
    }

    private const val MIN_CONTEXT_OCCURRENCES = 2
    private const val MIN_CONTEXT_LEAD = 2
}

/** Thread-safe, access-ordered cache with a strict cardinality limit. */
private class SageInlineLruCache<K : Any, V : Any>(private val limit: Int) {
    private val entries = object : LinkedHashMap<K, V>(limit, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<K, V>?): Boolean = size > limit
    }

    @Synchronized
    fun getOrPut(key: K, compute: () -> V): V = entries[key] ?: compute().also { entries[key] = it }
}
