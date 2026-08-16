package com.starnotesxj.sageide.sugar

import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.jetbrains.python.psi.PyAssignmentStatement

class SageSugarAnalyzerTest : BasePlatformTestCase() {

    private fun statements(fileName: String): Collection<PyAssignmentStatement> {
        myFixture.configureByFile("testData/sugar/$fileName")
        return PsiTreeUtil.collectElementsOfType(myFixture.file, PyAssignmentStatement::class.java)
    }

    fun testRecognizesBasicSugar() {
        val statements = statements("SageSugarBasic.sage")
        val first = statements.first()
        val info = SageSugarAnalyzer.analyze(first)!!

        assertEquals("R", info.factoryName)
        assertEquals(listOf("x"), info.names)
        assertEquals("GF", info.call?.callee?.name)
        assertTrue(first.targets.isEmpty())
        assertEquals(0, info.call!!.argumentList!!.arguments.size)

        val second = statements.elementAt(1)
        val secondInfo = SageSugarAnalyzer.analyze(second)!!
        assertEquals("F", secondInfo.factoryName)
        assertEquals(listOf("a"), secondInfo.names)
        assertEquals("GF", secondInfo.call?.callee?.name)
    }

    fun testRecognizesMultiNameSugar() {
        val info = SageSugarAnalyzer.analyze(statements("SageSugarMultiName.sage").first())!!
        assertEquals("K", info.factoryName)
        assertEquals(listOf("a", "b"), info.names)
        assertEquals("NumberField", info.call?.callee?.name)
    }

    fun testRejectsFalsePositives() {
        for (statement in statements("SageSugarFalsePositives.sage")) {
            assertNull(SageSugarAnalyzer.analyze(statement))
        }
    }

    fun testShapePredicateHoldsWhileRhsIsIncomplete() {
        val statement = statements("SageSugarBroken.sage").first()
        assertTrue(SageSugarAnalyzer.shapePredicate(statement))
        val info = SageSugarAnalyzer.analyze(statement)!!
        assertEquals("R", info.factoryName)
        assertNull(info.call)
    }

    fun testAnalyzerDeferForNonSageFiles() {
        myFixture.configureByText("plain.py", "R.<x> = GF(2)[]\n")
        val statement = PsiTreeUtil.findChildOfType(myFixture.file, PyAssignmentStatement::class.java)!!
        assertNull(SageSugarAnalyzer.analyze(statement))
    }
}
