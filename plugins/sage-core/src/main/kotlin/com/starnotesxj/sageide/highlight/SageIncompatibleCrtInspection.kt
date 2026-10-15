package com.starnotesxj.sageide.highlight

import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.psi.PsiElementVisitor
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyElementVisitor
import java.math.BigInteger

/** Reports four-literal CRT calls whose congruences cannot have a common solution. */
class SageIncompatibleCrtInspection : LocalInspectionTool() {

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PyElementVisitor() {
            override fun visitPyCallExpression(node: PyCallExpression) {
                if (node.callee?.text !in CRT_FUNCTION_NAMES) return
                val arguments = node.argumentList?.arguments.orEmpty()
                if (arguments.size != 4) return

                val values = arguments.map { SageIntegerLiteralParser.parse(it.text) }
                if (values.any { it == null }) return
                val (residueA, residueB, modulusM, modulusN) = values.filterNotNull()
                if (modulusM == BigInteger.ZERO || modulusN == BigInteger.ZERO) return

                val gcd = modulusM.gcd(modulusN)
                if (residueA.mod(gcd) == residueB.mod(gcd)) return

                holder.registerProblem(
                    node,
                    "No CRT solution: residues ${residueA.mod(gcd)} and ${residueB.mod(gcd)} " +
                        "disagree modulo gcd($modulusM, $modulusN) = $gcd.",
                    ProblemHighlightType.ERROR,
                )
            }
        }

    private companion object {
        val CRT_FUNCTION_NAMES = setOf("crt", "CRT")
    }
}
