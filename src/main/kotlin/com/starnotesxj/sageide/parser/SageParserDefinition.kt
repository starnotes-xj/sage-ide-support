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
     * Full caret lexical remapping to Sage preparse semantics (plan A):
     *
     * - `^^` — the Python lexer tokenizes it as two `^` tokens, a syntax
     *   error for the parser; the inner [MergingLexerAdapter] collapses the
     *   run into one XOR token (Python XOR semantics == Sage `^^`).
     * - the outer [SageCaretLexer] then remaps the remaining caret forms:
     *   single `^` -> EXP (Sage power, text stays "^"), `^=` -> EXPEQ
     *   (power assignment), `^^=` -> one XOREQ token (XOR assignment).
     *
     * After this, `e^254` parses as a power and follows the stubs' `__pow__`
     * type chain, `x ^^ y` / `x ^^= y` parse as bitwise XOR / XOR assignment,
     * and `x ^= y` parses as power assignment — exactly what the preparser
     * produces at runtime, while the displayed text never changes.
     */
    override fun createLexer(project: Project?): Lexer =
        SageCaretLexer {
            MergingLexerAdapter(super.createLexer(project), TokenSet.create(PyTokenTypes.XOR))
        }

    /**
     * The Sage file PSI: a [PyFileImpl] whose `getIcon()` returns the Sage
     * icon.  PyCharm 2026.1's PyFileImpl.getIcon() returns the Python icon
     * unconditionally and the project view short-circuits through it.
     */
    /**
     * The Sage file PSI: a [PyFileImpl] whose `getIcon()` returns the Sage
     * icon.  PyCharm 2026.1's PyFileImpl.getIcon() returns the Python icon
     * unconditionally and the project view short-circuits through it.
     */
    override fun createFile(viewProvider: FileViewProvider): PsiFile = SageFile(viewProvider)
}
