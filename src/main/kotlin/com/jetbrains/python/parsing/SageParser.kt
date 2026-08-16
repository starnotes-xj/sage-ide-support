package com.jetbrains.python.parsing

import com.intellij.lang.ASTNode
import com.intellij.lang.PsiBuilder
import com.intellij.lang.PsiParser
import com.intellij.lang.SyntaxTreeBuilder
import com.intellij.psi.tree.IElementType
import com.jetbrains.python.PyElementTypes
import com.jetbrains.python.PyParsingBundle
import com.jetbrains.python.PyTokenTypes

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
        val context = createParsingContext(builder, myLanguageLevel)
        val statementParser = context.statementParser
        builder.setTokenTypeRemapper(statementParser) // must be done before touching the caching lexer
        var lastAfterSemicolon = false
        while (!builder.eof()) {
            context.pushScope(context.emptyParsingScope())
            if (lastAfterSemicolon) {
                statementParser.parseSimpleStatement()
            }
            else if (looksLikeSugarStatement(builder)) {
                parseSugarStatement(context, builder)
            }
            else {
                statementParser.parseStatement()
            }
            lastAfterSemicolon = context.scope.isAfterSemicolon
            context.popScope()
        }
        rootMarker.done(root)
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
    private fun parseSugarStatement(context: ParsingContext, builder: SyntaxTreeBuilder): Boolean {
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
        if (!context.expressionParser.parseYieldOrTupleExpression(false)) {
            builder.error(PyParsingBundle.message("PARSE.expected.expression"))
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
