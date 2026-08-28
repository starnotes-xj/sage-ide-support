package com.starnotesxj.sageide.editor

import com.intellij.codeInsight.editorActions.TypedHandlerDelegate
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.fileTypes.FileType
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiFile
import com.starnotesxj.sageide.sugar.SageFileUtils

/**
 * Types the angle-bracket pair used by Sage generator sugar.
 *
 * Sage uses ``R.<x> = PolynomialRing(F)`` and similar statements.  The
 * Python/HTML typing handlers do not own this syntax, so a bare ``<`` would
 * otherwise leave the user to type the closing delimiter manually.  This
 * delegate deliberately works from the line prefix rather than from a class
 * or method name: it only fires after one simple assignment target followed by
 * a dot (``R.``), which is the lexical shape immediately before generator
 * sugar.  Comparisons, strings, comments and ordinary attribute chains are
 * left to the platform.
 */
class SageAngleBracketTypedHandler : TypedHandlerDelegate() {

    override fun beforeCharTyped(
        c: Char,
        project: Project,
        editor: Editor,
        file: PsiFile,
        fileType: FileType,
    ): Result {
        if (!SageFileUtils.isSageFile(file)) return Result.CONTINUE

        val document = editor.document
        val offset = editor.caretModel.offset.coerceIn(0, document.textLength)
        val linePrefix = linePrefix(document.charsSequence, offset)

        if (c == '<' && GENERATOR_PREFIX.matches(linePrefix)) {
            document.insertString(offset, "<>")
            editor.caretModel.moveToOffset(offset + 1)
            return Result.STOP
        }

        // The pair inserted above leaves the caret immediately before `>`.
        // Consume a manually typed closing delimiter so it does not become
        // `R.<x>>`; this is limited to the same generator-sugar line shape.
        if (c == '>' && offset < document.textLength &&
            document.charsSequence[offset] == '>' && GENERATOR_CONTENT.matches(linePrefix)
        ) {
            editor.caretModel.moveToOffset(offset + 1)
            return Result.STOP
        }

        return Result.CONTINUE
    }

    private fun linePrefix(chars: CharSequence, offset: Int): String {
        val lineStart = chars.subSequence(0, offset).lastIndexOf('\n') + 1
        return chars.subSequence(lineStart, offset).toString()
    }

    companion object {
        // Keep the trigger lexical and conservative.  The first target in a
        // Sage generator statement is a simple name (`R`, `F`, `K`, ...).
        private val GENERATOR_PREFIX = Regex("""^\s*[A-Za-z_]\w*\s*\.\s*$""")
        private val GENERATOR_CONTENT = Regex("""^\s*[A-Za-z_]\w*\s*\.\s*<[^<>]*$""")
    }
}
