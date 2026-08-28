package com.starnotesxj.sageide.editor

import com.starnotesxj.sageide.SagePluginTestBase
import com.intellij.codeInsight.editorActions.TypedHandlerDelegate
import com.intellij.openapi.command.WriteCommandAction
import kotlin.test.assertEquals

class SageAngleBracketTypedHandlerTest : SagePluginTestBase() {
    private val handler = SageAngleBracketTypedHandler()

    private fun beforeCharTyped(c: Char): TypedHandlerDelegate.Result {
        var result = TypedHandlerDelegate.Result.CONTINUE
        WriteCommandAction.runWriteCommandAction(myFixture.project) {
            result = handler.beforeCharTyped(c, myFixture.project, myFixture.editor, myFixture.file, myFixture.file.fileType)
        }
        return result
    }

    fun testLessThanPairsGeneratorSugarAndPlacesCaretInside() {
        myFixture.configureByText("generator.sage", "R.<caret> = PolynomialRing(F)\n")

        val result = beforeCharTyped('<')
        assertEquals(TypedHandlerDelegate.Result.STOP, result)

        assertEquals("R.<> = PolynomialRing(F)\n", myFixture.editor.document.text)
        assertEquals(3, myFixture.editor.caretModel.offset)
    }

    fun testClosingGreaterThanSkipsInsertedPair() {
        myFixture.configureByText("generator.sage", "R.<caret> = PolynomialRing(F)\n")

        beforeCharTyped('<')
        val result = beforeCharTyped('>')
        assertEquals(TypedHandlerDelegate.Result.STOP, result)

        assertEquals("R.<> = PolynomialRing(F)\n", myFixture.editor.document.text)
        assertEquals(4, myFixture.editor.caretModel.offset)
    }

    fun testComparisonDoesNotInsertClosingGreaterThan() {
        myFixture.configureByText("comparison.sage", "a <caret> b\n")

        val result = beforeCharTyped('<')
        assertEquals(TypedHandlerDelegate.Result.CONTINUE, result)
        val offset = myFixture.editor.caretModel.offset
        WriteCommandAction.runWriteCommandAction(myFixture.project) {
            myFixture.editor.document.insertString(offset, "<")
            myFixture.editor.caretModel.moveToOffset(offset + 1)
        }

        assertEquals("a < b\n", myFixture.editor.document.text)
        assertEquals(3, myFixture.editor.caretModel.offset)
    }
}
