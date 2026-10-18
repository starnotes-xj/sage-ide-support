package com.jetbrains.python.parsing

import com.intellij.lang.ASTNode
import com.intellij.lang.PsiBuilder
import com.intellij.lang.PsiParser
import com.intellij.lang.SyntaxTreeBuilder
import com.intellij.psi.tree.IElementType
import com.jetbrains.python.PyElementTypes
import com.jetbrains.python.PyParsingBundle
import com.jetbrains.python.PyTokenTypes
import com.jetbrains.python.psi.LanguageLevel

/**
 * The Python parser extended with Sage generator statements.
 *
 * `R.<x> = GF(2)[]` is intercepted before the Python statement parser sees
 * it (the `IDENT DOT LT` lookahead cannot start any valid Python
 * statement) and built as a real assignment tree: targets `[R, x]`, the
 * `DOT`/`LT`/`GT`/`EQ` tokens left as plain token leaves, and the RHS
 * parsed by the regular expression parser.  The resulting PSI is a
 * multi-target assignment, so type inference, resolve and completion all
 * work without any error-suppression hacks.
 *
 * Anything that does not match the sugar shape is delegated to the
 * original [PythonParser.parseRoot] flow verbatim.
 */
class SageParser : PythonParser(), PsiParser {

    override fun parse(root: IElementType, builder: PsiBuilder): ASTNode {
        parseRoot(root, builder as SyntaxTreeBuilder)
        return builder.treeBuilt
    }

    override fun parseRoot(root: IElementType, builder: SyntaxTreeBuilder) {
        val rootMarker = builder.mark()
        val context = SageParsingContext(builder, myLanguageLevel)
        val statementParser = context.statementParser
        builder.setTokenTypeRemapper(statementParser) // must be done before touching the caching lexer
        while (!builder.eof()) {
            context.pushScope(context.emptyParsingScope())
            // SageStatementParsing.parseStatement() intercepts generator
            // statements here AND inside every suite body, so the stock
            // after-semicolon/sugar/plain branching collapses into it.
            statementParser.parseStatement()
            context.popScope()
        }
        rootMarker.done(root)
    }

}

/**
 * Python's statement parser with one extra statement form: the Sage
 * generator declaration `X.<a, b> = rhs`.  parseStatement() is the
 * public dispatch point reached from the root loop AND from every
 * suite body (function/class bodies, if/for arms) — the suite loops
 * call it virtually — so intercepting here makes the sugar legal
 * wherever Sage allows it, not only at file top level.
 */
private class SageStatementParsing(
    private val sageContext: SageParsingContext,
) : StatementParsing(sageContext) {

    override fun parseStatement() {
        val builder = sageContext.builder
        // An editor reparses incomplete input after every keystroke.
        // `R.<` (or any other incomplete generator statement) rolls
        // its marker back and falls through to Python's parser so
        // parsing always advances; ignoring the fallback used to
        // spin forever on the EDT (frozen editor / freeze watchdog).
        if (looksLikeSugarStatement(builder) && parseSugarStatement(sageContext, builder)) {
            return
        }
        super.parseStatement()
    }

    private fun looksLikeSugarStatement(builder: SyntaxTreeBuilder): Boolean {
        return builder.tokenType === PyTokenTypes.IDENTIFIER &&
            builder.lookAhead(1) === PyTokenTypes.DOT &&
            builder.lookAhead(2) === PyTokenTypes.LT
    }

    /**
     * Builds `X.<a, b> = rhs` as a multi-target assignment.
     * Returns false (after rollback) when the shape does not complete, so
     * the caller falls back to the normal Python statement parser.
     */
    private fun parseSugarStatement(context: SageParsingContext, builder: SyntaxTreeBuilder): Boolean {
        val marker = builder.mark()
        buildTarget(builder) // the factory target, e.g. R or F
        builder.advanceLexer() // DOT — plain token leaf
        builder.advanceLexer() // LT — plain token leaf
        while (true) {
            if (builder.tokenType !== PyTokenTypes.IDENTIFIER) {
                marker.rollbackTo()
                return false
            }
            buildTarget(builder) // generator names
            if (builder.tokenType === PyTokenTypes.COMMA) {
                builder.advanceLexer()
            }
            else {
                break
            }
        }
        if (builder.tokenType !== PyTokenTypes.GT) {
            marker.rollbackTo()
            return false
        }
        builder.advanceLexer() // GT — plain token leaf
        if (builder.tokenType !== PyTokenTypes.EQ) {
            marker.rollbackTo()
            return false
        }
        builder.advanceLexer() // EQ — must stay a token leaf: calcTargets scans up to it
        // Sage's generator declaration gives the trailing empty `[]` its
        // generator names (R.<x> = GF(2)[]). Python's ordinary subscription
        // parser rejects a zero-item index list, so enable that one form only
        // while parsing this assignment's RHS.
        context.allowGeneratorEmptySubscription = true
        try {
            if (!context.expressionParser.parseYieldOrTupleExpression(false)) {
                builder.error(PyParsingBundle.message("PARSE.expected.expression"))
            }
        } finally {
            context.allowGeneratorEmptySubscription = false
        }
        checkEndOfStatement(context, builder)
        marker.done(PyElementTypes.ASSIGNMENT_STATEMENT)
        return true
    }

    private fun buildTarget(builder: SyntaxTreeBuilder) {
        val marker = builder.mark()
        builder.advanceLexer()
        marker.done(PyElementTypes.TARGET_EXPRESSION)
    }

    /** Mirrors StatementParsing.checkEndOfStatement for statement-level use. */
    private fun checkEndOfStatement(context: ParsingContext, builder: SyntaxTreeBuilder) {
        val scope = context.scope
        if (builder.tokenType === PyTokenTypes.STATEMENT_BREAK) {
            builder.advanceLexer()
            scope.setAfterSemicolon(false)
        }
        else if (builder.tokenType === PyTokenTypes.SEMICOLON) {
            if (!scope.isSuite) {
                builder.advanceLexer()
                scope.setAfterSemicolon(true)
                if (builder.tokenType === PyTokenTypes.STATEMENT_BREAK) {
                    builder.advanceLexer()
                    scope.setAfterSemicolon(false)
                }
            }
        }
        else if (!builder.eof()) {
            builder.error(PyParsingBundle.message("end.of.statement.expected"))
        }
    }
}

/** Shares Python's parser and PSI, with one Sage generator-RHS grammar exception. */
private class SageParsingContext(builder: SyntaxTreeBuilder, level: LanguageLevel) : ParsingContext(builder, level) {
    var allowGeneratorEmptySubscription = false

    private val sageExpressionParser = object : ExpressionParsing(this) {
        override fun parseSubscriptionIndexArgumentList() {
            val next = builder.lookAhead(1)
            if (allowGeneratorEmptySubscription &&
                builder.tokenType === PyTokenTypes.RBRACKET &&
                (next == null || next === PyTokenTypes.STATEMENT_BREAK || next === PyTokenTypes.SEMICOLON)
            ) {
                builder.advanceLexer()
                return
            }
            super.parseSubscriptionIndexArgumentList()
        }
    }

    private val sageStatementParser = SageStatementParsing(this)

    override fun getStatementParser(): StatementParsing = sageStatementParser

    override fun getExpressionParser(): ExpressionParsing = sageExpressionParser
}
