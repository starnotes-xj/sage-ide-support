package com.starnotesxj.sageide.sugar

import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.PyTokenTypes
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PySubscriptionExpression
import com.jetbrains.python.psi.PyTargetExpression

/**
 * Recognizes Sage generator statements in the PSI produced by [SageParser].
 *
 * The Sage parser builds `F.<a> = GF(2^8, ...)` as a plain multi-target
 * assignment: targets `[F, a]` with the `DOT`/`LT`/`GT`/`EQ` tokens left as
 * plain token leaves directly under the statement.  The presence of an `LT`
 * leaf at statement level is what distinguishes sugar statements from
 * ordinary `a, b = ...` unpacking, so [shapePredicate] checks exactly that.
 */
object SageSugarAnalyzer {

    fun shapePredicate(statement: PyAssignmentStatement): Boolean {
        if (!SageFileUtils.isSageFile(statement.containingFile)) return false
        return statement.node.findChildByType(PyTokenTypes.LT) != null
    }

    fun analyze(statement: PyAssignmentStatement): SageSugarInfo? {
        if (!shapePredicate(statement)) return null
        val targets = statement.targets.filterIsInstance<PyTargetExpression>()
        val factoryTarget = targets.firstOrNull() ?: return null
        if (factoryTarget.name == null) return null
        return SageSugarInfo(
            statement = statement,
            factoryTarget = factoryTarget,
            call = unwrapCall(statement.assignedValue),
            nameTargets = targets.drop(1),
        )
    }

    fun analyzeForTarget(target: PyTargetExpression): SageSugarInfo? {
        val statement = PsiTreeUtil.getParentOfType(target, PyAssignmentStatement::class.java) ?: return null
        return analyze(statement)
    }

    /** `GF(2)[]` parses as a subscription with an empty index; unwrap to the call. */
    private fun unwrapCall(expression: PsiElement?): PyCallExpression? {
        return when (expression) {
            is PyCallExpression -> expression
            is PySubscriptionExpression -> expression.operand as? PyCallExpression
            else -> null
        }
    }
}
