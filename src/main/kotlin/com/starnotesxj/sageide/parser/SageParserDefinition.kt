package com.starnotesxj.sageide.parser

import com.intellij.lang.PsiParser
import com.intellij.lexer.Lexer
import com.intellij.lexer.MergingLexerAdapter
import com.intellij.openapi.project.Project
import com.intellij.psi.FileViewProvider
import com.intellij.psi.PsiFile
import com.intellij.psi.tree.IFileElementType
import com.intellij.psi.tree.TokenSet
import com.jetbrains.python.PyTokenTypes
import com.jetbrains.python.PythonParserDefinition
import com.jetbrains.python.parsing.SageParser
import com.starnotesxj.sageide.sugar.SageFile
import com.starnotesxj.sageide.sugar.SageFileElementType

/**
 * Parser definition for the Sage dialect.  Reuses the Python parser
 * definition for everything (file PSI, element creation, comment and
 * whitespace tokens) and only swaps the parser and the file node type.
 */
class SageParserDefinition : PythonParserDefinition() {

    override fun getFileNodeType(): IFileElementType = SageFileElementType.INSTANCE

    override fun createParser(project: Project?): PsiParser = SageParser()

    /**
     * Sage's XOR spelling is `^^`, which the Python lexer tokenizes as two
     * `^` tokens — a syntax error for the Python parser.  Merge consecutive
     * XOR tokens into one, so `x ^^ y` parses as a single XOR expression
     * (Python XOR semantics == Sage `^^` semantics) and the file stops
     * showing spurious "expression expected" errors.
     *
     * (`^` alone stays a Python XOR token; Sage power semantics for it can
     * come later from a dedicated lexer remapping `^` to `**`.)
     */
    override fun createLexer(project: Project?): Lexer =
        MergingLexerAdapter(super.createLexer(project), TokenSet.create(PyTokenTypes.XOR))

    /**
     * The Sage file PSI: a [PyFileImpl] whose `getIcon()` returns the Sage
     * icon.  PyCharm 2026.1's PyFileImpl.getIcon() returns the Python icon
     * unconditionally and the project view short-circuits through it.
     */
    override fun createFile(viewProvider: FileViewProvider): PsiFile = SageFile(viewProvider)
}
