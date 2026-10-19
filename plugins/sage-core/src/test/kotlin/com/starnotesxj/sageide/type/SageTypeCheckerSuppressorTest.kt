package com.starnotesxj.sageide.type

import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.starnotesxj.sageide.SagePluginTestBase

/**
 * The provider types a `.sage` target assigned a bare numeric literal as the
 * preparse-converted Sage class ([SageTypeProvider.literalAssignedType]); the
 * checker then compares the raw PSI literal against it.  The preparser wraps
 * the RHS in the same class at runtime, so the diagnostic is always false and
 * the suppressor must hide it — without touching ordinary assignments.
 *
 * JUnit3 assertions take the message FIRST (inherited from
 * junit.framework.Assert, which shadows kotlin.test).
 */
class SageTypeCheckerSuppressorTest : SagePluginTestBase() {
    private val suppressor = SageTypeCheckerSuppressor()

    fun testBareIntegerLiteralAssignmentIsSuppressedInSageFile() {
        val file = myFixture.configureByText(
            "numeric-literal.sage",
            "ct = 134217728\ns = 0\n",
        )
        val statements = PsiTreeUtil.collectElementsOfType(file, PyAssignmentStatement::class.java).toList()
        assertEquals(2, statements.size)
        for (statement in statements) {
            val assigned = statement.assignedValue
            assertNotNull(assigned)
        val target = assigned!!
            assertTrue(
                "integer literal assignment must be suppressed: ${statement.text}",
                suppressor.isSuppressedFor(target, "PyTypeChecker"),
            )
            assertTrue(
                "statement-registered problems must be suppressed too: ${statement.text}",
                suppressor.isSuppressedFor(statement, "PyTypeChecker"),
            )
        }
    }

    fun testBareFloatLiteralAssignmentIsSuppressedInSageFile() {
        val file = myFixture.configureByText("numeric-float.sage", "x = 1.5\n")
        val statement = PsiTreeUtil.collectElementsOfType(file, PyAssignmentStatement::class.java).single()
        val assigned = statement.assignedValue
        assertNotNull(assigned)
        val target = assigned!!
        assertTrue("float literal assignment must be suppressed", suppressor.isSuppressedFor(target, "PyTypeCheckerInspection"))
    }

    fun testCallAssignmentIsNotSuppressed() {
        val file = myFixture.configureByText(
            "call-target.sage",
            "values = {}\nvalues['N'] = Integer(3599)\n",
        )
        val statements = PsiTreeUtil.collectElementsOfType(file, PyAssignmentStatement::class.java).toList()
        assertEquals(2, statements.size)
        for (statement in statements) {
            val assigned = statement.assignedValue
            assertNotNull(assigned)
        val target = assigned!!
            assertFalse(
                "non-literal RHS keeps native checking: ${statement.text}",
                suppressor.isSuppressedFor(target, "PyTypeChecker"),
            )
        }
    }

    fun testNumericLiteralAssignmentInPythonFileIsNotSuppressed() {
        val file = myFixture.configureByText("plain.py", "x = 5\n")
        val statement = PsiTreeUtil.collectElementsOfType(file, PyAssignmentStatement::class.java).single()
        val assigned = statement.assignedValue
        assertNotNull(assigned)
        val target = assigned!!
        assertFalse(
            "the literal rule is Sage-preparse semantics, not a Python rule",
            suppressor.isSuppressedFor(target, "PyTypeChecker"),
        )
    }

    fun testOtherInspectionsAreNotSuppressed() {
        val file = myFixture.configureByText("other-inspection.sage", "ct = 134217728\n")
        val statement = PsiTreeUtil.collectElementsOfType(file, PyAssignmentStatement::class.java).single()
        val assigned = statement.assignedValue
        assertNotNull(assigned)
        val target = assigned!!
        assertFalse("other inspections keep running", suppressor.isSuppressedFor(target, "PyDictCreationInspection"))
        assertFalse("other inspections keep running", suppressor.isSuppressedFor(target, "PyUnresolvedReferences"))
    }

    fun testGeneratorSugarAssignmentIsStillSuppressed() {
        val file = myFixture.configureByText("generator-sugar.sage", "R.<x> = PolynomialRing(GF(2))\n")
        val statement = PsiTreeUtil.collectElementsOfType(file, PyAssignmentStatement::class.java).single()
        val assigned = statement.assignedValue
        assertNotNull(assigned)
        val target = assigned!!
        assertTrue(
            "the pre-existing generator-sugar suppression must keep working",
            suppressor.isSuppressedFor(target, "PyTypeChecker"),
        )
    }
}
