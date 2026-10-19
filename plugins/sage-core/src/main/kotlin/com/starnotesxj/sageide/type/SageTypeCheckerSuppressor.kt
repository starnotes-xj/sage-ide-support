package com.starnotesxj.sageide.type

import com.intellij.codeInspection.InspectionSuppressor
import com.intellij.codeInspection.SuppressQuickFix
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyNumericLiteralExpression
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer

/**
 * Prevents Python's type checker from flagging Sage-only assignment semantics.
 *
 * 1. Generator sugar ``R.<x> = PolynomialRing(F)`` is represented by the
 *    Python PSI as targets ``R, x`` and one RHS expression.  The RHS is the
 *    ring while the second target is the ring's generator, so the native
 *    checker quite correctly sees a mismatch for Python syntax but not for
 *    Sage semantics.  The provider still exposes the exact types for both
 *    targets; this suppressor only hides the single assignment diagnostic
 *    attached to that shared RHS expression.
 *
 * 2. A bare numeric literal assignment (``s = 0``, ``ct = 134217728``) is
 *    typed by [SageTypeProvider.literalAssignedType] as the preparse-
 *    converted Sage class (``Integer`` / ``RealNumber``).  The checker then
 *    compares the raw PSI literal (``Literal[0]``) against that target type
 *    and reports a mismatch — but the Sage preparser converts the RHS to the
 *    same class at runtime (verified against ``sage.repl.preparse``: ``x = 5``
 *    executes as ``x = Integer(5)``), so the mismatch cannot occur in
 *    practice and the diagnostic is always false inside `.sage` files.
 */
class SageTypeCheckerSuppressor : InspectionSuppressor {
    override fun isSuppressedFor(element: PsiElement, toolId: String): Boolean {
        if (toolId != "PyTypeChecker" && toolId != "PyTypeCheckerInspection") return false
        val statement = if (element is PyAssignmentStatement) {
            element
        } else {
            PsiTreeUtil.getParentOfType(element, PyAssignmentStatement::class.java) ?: return false
        }
        if (SageSugarAnalyzer.shapePredicate(statement)) {
            if (element !== statement.assignedValue) return false
            return SageSugarAnalyzer.analyze(statement)?.nameTargets?.isNotEmpty() == true
        }
        // Bare numeric literal assignment: the preparser wraps the RHS in the
        // same class the provider assigned to the target, so the literal-vs-
        // Sage-class comparison can never correspond to a runtime mismatch.
        // Problems may be registered on the assigned value or the statement.
        if (!SageFileUtils.isSageFile(statement.containingFile)) return false
        val assigned = statement.assignedValue ?: return false
        if (assigned !is PyNumericLiteralExpression) return false
        return element === assigned || element === statement
    }

    override fun getSuppressActions(element: PsiElement?, toolId: String): Array<out SuppressQuickFix> =
        SuppressQuickFix.EMPTY_ARRAY
}
