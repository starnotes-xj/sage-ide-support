package com.starnotesxj.sageide.highlight

import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.psi.PsiElementVisitor
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyElementVisitor
import java.math.BigInteger

/** Reports literal finite-field cardinalities that Sage can prove are invalid. */
class SageFiniteFieldOrderInspection : LocalInspectionTool() {

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PyElementVisitor() {
            override fun visitPyCallExpression(node: PyCallExpression) {
                if (node.callee?.text?.substringAfterLast('.') !in FIELD_CONSTRUCTORS) return
                val orderArgument = node.argumentList?.arguments?.firstOrNull() ?: return
                val order = parseSmallInteger(orderArgument.text) ?: return

                if (order < TWO || !isPrimePower(order)) {
                    holder.registerProblem(
                        orderArgument,
                        "A finite field must have prime-power cardinality; '$order' is not a valid field order.",
                        ProblemHighlightType.ERROR,
                    )
                }
            }
        }

    private fun parseSmallInteger(text: String): BigInteger? {
        if (text.length > MAX_LITERAL_LENGTH) return null
        var normalized = text.trim().lowercase()
        val sign = when {
            normalized.startsWith('-') -> BigInteger.ONE.negate()
            normalized.startsWith('+') -> BigInteger.ONE
            else -> BigInteger.ONE
        }
        if (normalized.startsWith('+') || normalized.startsWith('-')) {
            normalized = normalized.drop(1).trimStart()
        }
        // Accept one unary sign only; leave compound expressions to SageMath.
        if (normalized.startsWith('+') || normalized.startsWith('-')) return null
        val (prefix, radix, literalPattern) = when {
            normalized.startsWith("0x") -> Triple("0x", 16, HEX_INTEGER_PATTERN)
            normalized.startsWith("0o") -> Triple("0o", 8, OCTAL_INTEGER_PATTERN)
            normalized.startsWith("0b") -> Triple("0b", 2, BINARY_INTEGER_PATTERN)
            else -> Triple("", 10, DECIMAL_INTEGER_PATTERN)
        }
        if (!literalPattern.matches(normalized)) return null
        val digits = normalized.removePrefix(prefix).replace("_", "")
        val magnitude = runCatching { BigInteger(digits, radix) }.getOrNull() ?: return null
        if (magnitude > MAX_PROVEN_ORDER) return null
        return magnitude.multiply(sign)
    }

    /** Complete trial division is bounded by MAX_PROVEN_ORDER (~1K iterations worst case). */
    private fun isPrimePower(value: BigInteger): Boolean {
        if (value < TWO) return false
        var factor = TWO
        var remainder = value
        while (factor * factor <= remainder) {
            if (remainder.mod(factor) == BigInteger.ZERO) {
                do {
                    remainder = remainder.divide(factor)
                } while (remainder.mod(factor) == BigInteger.ZERO)
                return remainder == BigInteger.ONE
            }
            factor = factor.add(BigInteger.ONE)
        }
        return true
    }

    private companion object {
        val FIELD_CONSTRUCTORS = setOf("GF", "FiniteField")
        val TWO = BigInteger.valueOf(2)
        val MAX_PROVEN_ORDER = BigInteger.valueOf(1_000_000L)
        val DECIMAL_INTEGER_PATTERN = Regex("(?:0(?:_?0)*|[1-9](?:_?[0-9])*)")
        val BINARY_INTEGER_PATTERN = Regex("0b_?[01](?:_?[01])*")
        val OCTAL_INTEGER_PATTERN = Regex("0o_?[0-7](?:_?[0-7])*")
        val HEX_INTEGER_PATTERN = Regex("0x_?[0-9a-f](?:_?[0-9a-f])*")
        const val MAX_LITERAL_LENGTH = 16
    }
}
