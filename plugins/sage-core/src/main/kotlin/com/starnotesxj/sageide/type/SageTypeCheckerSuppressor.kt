package com.starnotesxj.sageide.type

import com.intellij.codeInspection.InspectionSuppressor
import com.intellij.codeInspection.SuppressQuickFix
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer

/**
 * Prevents Python's tuple-assignment checker from treating Sage generator
 * sugar as an ordinary unpacking assignment.
 *
 * ``R.<x> = PolynomialRing(F)`` is represented by the Python PSI as targets
 * ``R, x`` and one RHS expression.  The RHS is the ring while the second
 * target is the ring's generator, so the native checker quite correctly sees
 * a mismatch for Python syntax but not for Sage semantics.  The provider
 * still exposes the exact types for both targets; this suppressor only hides
 * the single assignment diagnostic attached to that shared RHS expression.
 */
class SageTypeCheckerSuppressor : InspectionSuppressor {
    override fun isSuppressedFor(element: PsiElement, toolId: String): Boolean {
        if (toolId != "PyTypeChecker" && toolId != "PyTypeCheckerInspection") return false
        val statement = PsiTreeUtil.getParentOfType(element, PyAssignmentStatement::class.java) ?: return false
        if (!SageSugarAnalyzer.shapePredicate(statement)) return false
        if (element !== statement.assignedValue) return false
        return SageSugarAnalyzer.analyze(statement)?.nameTargets?.isNotEmpty() == true
    }

    override fun getSuppressActions(element: PsiElement?, toolId: String): Array<out SuppressQuickFix> =
        SuppressQuickFix.EMPTY_ARRAY
}
