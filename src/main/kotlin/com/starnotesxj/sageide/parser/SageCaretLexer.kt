package com.starnotesxj.sageide.parser

import com.intellij.lexer.Lexer
import com.intellij.lexer.LexerBase
import com.intellij.psi.tree.IElementType
import com.intellij.psi.tree.TokenSet
import com.jetbrains.python.PyTokenTypes

/**
 * Lexical caret remapping for the Sage dialect (the "full plan A"): make the
 * IDE token stream match what the Sage preparser produces, so `.sage` files
 * parse with Sage semantics while the on-screen text never changes.
 *
 * The delegate is a [com.intellij.lexer.MergingLexerAdapter] over the Python
 * lexer that collapses `^^` runs into one XOR token, so the incoming stream
 * here is:
 *
 * | text  | incoming token | emitted token | Sage preparse meaning     |
 * |-------|----------------|---------------|---------------------------|
 * | `^`   | XOR            | EXP           | power (`**`)              |
 * | `^^`  | XOR (merged)   | XOR           | bitwise XOR (`^`)         |
 * | `^=`  | XOREQ          | EXPEQ         | power assignment (`**=`)  |
 * | `^^=` | XOR then XOREQ | XOREQ (merged)| XOR assignment (`^=`)     |
 *
 * The token **text** is never rewritten — only the AST semantic changes, so
 * `e^254` parses as a power and follows the stubs' `__pow__` type chain.
 *
 * Implementation notes (all hard-won, see HANDOFF):
 *
 * - **Lookahead = restart a FRESH scratch instance per peek.** The delegate's
 *   `MergingLexerAdapterBase.advance()` is lazy (real movement happens on the
 *   next `getTokenType()`), so "two lockstep instances" fall behind and peek
 *   stale tokens.  And `PythonIndentingProcessor.start()` does NOT clear its
 *   pending-token queue (`myTokenQueue`) or other line-tracking state: a
 *   REUSED scratch instance that once restarted on whitespace keeps returning
 *   stale INDENT/SPACE pending tokens for every later peek — exactly the bug
 *   that made `m ^^=1` fail in a long file while a minimal file was fine.
 *   A brand-new factory instance per peek has no history at all, so nothing
 *   can leak.  (One flex lexer allocation per `^` — cheap, no re-lexing.)
 *
 * - The peek result is only used for the `=== XOREQ` / is-XOR test, where
 *   even odd answers (INDENT pending tokens from the reset indent stack,
 *   etc.) fall through correctly.
 *
 * - **The `^^=` merge consumes two delegate tokens**, and skipping them must
 *   be done explicitly: `tokenType` query + `advance()` twice, because plain
 *   `advance()` calls are lazy no-ops at the underlying level.
 *
 * Known degenerate: `^^^` (Sage preparses it to `^ **`) stays a single XOR
 * token; nobody writes that, and the merged run keeps the file parseable.
 */
class SageCaretLexer(private val delegateFactory: () -> Lexer) : LexerBase() {

    private val myDelegate: Lexer = delegateFactory()

    // The token currently exposed to the parser.
    private var myTokenType: IElementType? = null
    private var myTokenStart = 0
    private var myTokenEnd = 0
    /** True when the exposed token consumed two delegate tokens (`^^=`). */
    private var myMergedXorEq = false

    // Peek cache for the current delegate token.
    private var myAheadCached = false
    private var myAheadTokenType: IElementType? = null
    private var myAheadTokenStart = 0
    private var myAheadTokenEnd = 0

    override fun start(buffer: CharSequence, startOffset: Int, endOffset: Int, initialState: Int) {
        myDelegate.start(buffer, startOffset, endOffset, initialState)
        myTokenType = null
        myTokenStart = 0
        myTokenEnd = 0
        myMergedXorEq = false
        myAheadCached = false
        myAheadTokenType = null
        myAheadTokenStart = 0
        myAheadTokenEnd = 0
    }

    override fun getState(): Int = myDelegate.state

    override fun getTokenType(): IElementType? {
        if (myTokenType != null) return myTokenType
        val delegateType = myDelegate.tokenType
        if (delegateType == null) {
            myTokenType = null
            return null
        }
        myTokenStart = myDelegate.tokenStart
        myTokenEnd = myDelegate.tokenEnd
        myMergedXorEq = false

        if (isXor(delegateType)) {
            if (myTokenEnd - myTokenStart == 1) {
                // A single `^` — but it may be the first half of `^^=`.
                val next = lookAhead()
                if (next === PyTokenTypes.XOREQ) {
                    // `^^=`: merge the two delegate tokens into one XOREQ
                    // token (bitwise XOR assignment in Sage).
                    myTokenType = PyTokenTypes.XOREQ
                    myTokenEnd = myAheadTokenEnd
                    myMergedXorEq = true
                    return myTokenType
                }
                if (next != null && isXor(next)) {
                    // `^^` on a platform whose merge layer reports each caret
                    // separately: keep both as XOR; the builder merges them.
                    myTokenType = delegateType
                    return myTokenType
                }
                // A lone `^`: Sage power.
                myTokenType = PyTokenTypes.EXP
                return myTokenType
            }
            // A merged `^^...` run: Sage bitwise XOR.
            myTokenType = delegateType
            return myTokenType
        }

        if (delegateType === PyTokenTypes.XOREQ) {
            // `^=`: Sage power assignment.
            myTokenType = PyTokenTypes.EXPEQ
            return myTokenType
        }

        myTokenType = delegateType
        return myTokenType
    }

    override fun getTokenStart(): Int {
        if (myTokenType == null) getTokenType()
        return myTokenStart
    }

    override fun getTokenEnd(): Int {
        if (myTokenType == null) getTokenType()
        return myTokenEnd
    }

    override fun advance() {
        myTokenType = null
        val merged = myMergedXorEq
        myMergedXorEq = false
        myAheadCached = false
        myAheadTokenType = null
        myAheadTokenStart = 0
        myAheadTokenEnd = 0
        if (merged) {
            // The exposed token covered two delegate tokens (XOR + XOREQ).
            // The delegate advances lazily (real movement happens on the
            // next getTokenType()), so skip both tokens explicitly:
            // query + advance for each.
            myDelegate.tokenType
            myDelegate.advance()
            myDelegate.tokenType
            myDelegate.advance()
        }
        else {
            myDelegate.advance()
        }
    }

    override fun getBufferEnd(): Int = myDelegate.bufferEnd

    override fun getBufferSequence(): CharSequence = myDelegate.bufferSequence

    private fun lookAhead(): IElementType? {
        if (!myAheadCached) {
            // Fresh instance per peek: PythonIndentingProcessor.start() does
            // not clear its pending-token queue, so a reused scratch lexer
            // leaks stale INDENT/SPACE tokens across restarts (see class
            // docs — this was the "^^= broken only in long files" bug).
            val scratch = delegateFactory()
            scratch.start(myDelegate.bufferSequence, myDelegate.tokenEnd, myDelegate.bufferEnd, myDelegate.state)
            myAheadTokenType = scratch.tokenType
            myAheadTokenStart = scratch.tokenStart
            myAheadTokenEnd = scratch.tokenEnd
            myAheadCached = true
        }
        return myAheadTokenType
    }

    companion object {
        private val XOR_TOKENS: TokenSet = TokenSet.create(PyTokenTypes.XOR)

        /**
         * Covers both a plain XOR token and the merged-token form used by
         * older `MergingLexerAdapter` implementations.
         */
        private fun isXor(type: IElementType): Boolean =
            type === PyTokenTypes.XOR || XOR_TOKENS.contains(type)
    }
}
