package com.starnotesxj.sageide.highlight

import com.intellij.psi.PsiErrorElement
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.jetbrains.python.psi.PyAssignmentStatement
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer

class SageSugarErrorFilterTest : BasePlatformTestCase() {

    private val filter = SageSugarErrorFilter()

    fun testSuppressesErrorsInsideSugarStatements() {
        myFixture.configureByFile("testData/sugar/SageSugarBasic.sage")
        for (error in PsiTreeUtil.collectElementsOfType(myFixture.file, PsiErrorElement::class.java)) {
            val statement = PsiTreeUtil.getParentOfType(error, PyAssignmentStatement::class.java)
            val inSugar = statement != null && SageSugarAnalyzer.shapePredicate(statement)
            if (inSugar) {
                assertFalse("error inside sugar statement must be suppressed", filter.shouldHighlightErrorElement(error))
            }
        }
    }

    fun testKeepsErrorsInPlainPythonFiles() {
        myFixture.configureByText("plain.py", "def broken( -> int: ...\n")
        for (error in PsiTreeUtil.collectElementsOfType(myFixture.file, PsiErrorElement::class.java)) {
            assertTrue(filter.shouldHighlightErrorElement(error))
        }
    }

    fun testKeepsErrorsOutsideSugarStatements() {
        myFixture.configureByFile("testData/sugar/SageSugarFalsePositives.sage")
        for (error in PsiTreeUtil.collectElementsOfType(myFixture.file, PsiErrorElement::class.java)) {
            assertTrue(filter.shouldHighlightErrorElement(error))
        }
    }
}
