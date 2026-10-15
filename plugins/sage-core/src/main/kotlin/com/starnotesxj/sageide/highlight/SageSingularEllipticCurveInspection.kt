package com.starnotesxj.sageide.highlight

import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.psi.PsiElementVisitor
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyElementVisitor
import com.jetbrains.python.psi.PyExpression
import com.jetbrains.python.psi.PySequenceExpression
import java.math.BigInteger

/** Finds Weierstrass models whose singularity is provable from small integer literals. */
class SageSingularEllipticCurveInspection : LocalInspectionTool() {

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PyElementVisitor() {
            override fun visitPyCallExpression(node: PyCallExpression) {
                if (node.callee?.text?.substringAfterLast('.') != ELLIPTIC_CURVE) return
                val arguments = node.argumentList?.arguments ?: return
                if (arguments.size !in 1..2) return

                val coefficients = arguments.lastOrNull() as? PySequenceExpression ?: return
                val values = when (coefficients.elements.size) {
                    2 -> listOf(BigInteger.ZERO, BigInteger.ZERO, BigInteger.ZERO) +
                        coefficients.elements.map { parseSmallInteger(it) ?: return }
                    5 -> coefficients.elements.map { parseSmallInteger(it) ?: return }
                    else -> return
                }
                val discriminant = discriminant(values)

                val singular = when (arguments.size) {
                    // Sage coerces literal integer coefficients to QQ in the one-argument form.
                    1 -> discriminant == BigInteger.ZERO
                    2 -> {
                        val characteristic = explicitBaseCharacteristic(arguments[0]) ?: return
                        characteristic == BigInteger.ZERO && discriminant == BigInteger.ZERO ||
                            characteristic > BigInteger.ONE && discriminant.mod(characteristic) == BigInteger.ZERO
                    }
                    else -> false
                }
                if (!singular) return

                holder.registerProblem(
                    coefficients,
                    "This Weierstrass model is singular for the specified base field.",
                    ProblemHighlightType.ERROR,
                )
            }
        }

    private fun discriminant(a: List<BigInteger>): BigInteger {
        val (a1, a2, a3, a4, a6) = a
        val b2 = a1.pow(2) + FOUR * a2
        val b4 = a1 * a3 + TWO * a4
        val b6 = a3.pow(2) + FOUR * a6
        val b8 = a1.pow(2) * a6 + FOUR * a2 * a6 - a1 * a3 * a4 + a2 * a3.pow(2) - a4.pow(2)
        return -b2.pow(2) * b8 - EIGHT * b4.pow(3) - TWENTY_SEVEN * b6.pow(2) + NINE * b2 * b4 * b6
    }

    private fun explicitBaseCharacteristic(expression: PyExpression): BigInteger? {
        if (expression.text == "QQ" || expression.text == "sage.rings.rational_field.QQ") {
            return BigInteger.ZERO
        }
        val fieldCall = expression as? PyCallExpression ?: return null
        if (fieldCall.callee?.text?.substringAfterLast('.') !in FIELD_CONSTRUCTORS) return null
        val orderExpression = fieldCall.argumentList?.arguments?.firstOrNull() ?: return null
        val order = parseSmallInteger(orderExpression) ?: return null
        if (order < TWO) return null

        var factor = TWO
        var remainder = order
        while (factor * factor <= remainder) {
            if (remainder.mod(factor) == BigInteger.ZERO) {
                do {
                    remainder = remainder.divide(factor)
                } while (remainder.mod(factor) == BigInteger.ZERO)
                return factor.takeIf { remainder == BigInteger.ONE }
            }
            factor = factor.add(BigInteger.ONE)
        }
        return remainder // The order itself is prime.
    }

    private fun parseSmallInteger(expression: PyExpression): BigInteger? {
        val text = expression.text.replace("_", "").lowercase()
        if (text.length > MAX_LITERAL_LENGTH) return null
        val negative = text.startsWith('-')
        val unsigned = if (negative) text.drop(1) else text
        val (digits, radix) = when {
            unsigned.startsWith("0x") -> unsigned.drop(2) to 16
            unsigned.startsWith("0o") -> unsigned.drop(2) to 8
            unsigned.startsWith("0b") -> unsigned.drop(2) to 2
            else -> unsigned to 10
        }
        if (digits.isEmpty()) return null
        val value = runCatching { BigInteger(digits, radix) }.getOrNull() ?: return null
        val signedValue = if (negative) value.negate() else value
        return signedValue.takeIf { it.abs() <= MAX_PROVEN_LITERAL }
    }

    private companion object {
        const val ELLIPTIC_CURVE = "EllipticCurve"
        const val MAX_LITERAL_LENGTH = 16
        val FIELD_CONSTRUCTORS = setOf("GF", "FiniteField")
        val TWO = BigInteger.valueOf(2)
        val FOUR = BigInteger.valueOf(4)
        val EIGHT = BigInteger.valueOf(8)
        val NINE = BigInteger.valueOf(9)
        val TWENTY_SEVEN = BigInteger.valueOf(27)
        val MAX_PROVEN_LITERAL = BigInteger.valueOf(1_000_000L)
    }
}
