package com.starnotesxj.sageide.highlight

import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.psi.PsiElementVisitor
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyElementVisitor
import java.math.BigInteger

internal object SageIntegerLiteralParser {
    private const val MAX_LITERAL_LENGTH = 256
    private val INTEGER_LITERAL = Regex(
        """[+-]?(?:0[xX][0-9a-fA-F](?:_?[0-9a-fA-F])*|0[oO][0-7](?:_?[0-7])*|0[bB][01](?:_?[01])*|[0-9](?:_?[0-9])*)""",
    )

    fun parse(text: String): BigInteger? {
        if (text.length > MAX_LITERAL_LENGTH || !INTEGER_LITERAL.matches(text)) return null
        val normalized = text.replace("_", "").lowercase()
        val negative = normalized.startsWith("-")
        val unsigned = normalized.removePrefix("-").removePrefix("+")
        val (digits, radix) = when {
            unsigned.startsWith("0x") -> unsigned.drop(2) to 16
            unsigned.startsWith("0o") -> unsigned.drop(2) to 8
            unsigned.startsWith("0b") -> unsigned.drop(2) to 2
            else -> unsigned to 10
        }
        val value = runCatching { BigInteger(digits, radix) }.getOrNull() ?: return null
        return if (negative) value.negate() else value
    }
}

/** Reports `inverse_mod(a, m)` only when integer literals prove gcd(a, m) != 1. */
class SageNonInvertibleModularInverseInspection : LocalInspectionTool() {

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PyElementVisitor() {
            override fun visitPyCallExpression(node: PyCallExpression) {
                if (node.callee?.text != INVERSE_MOD) return
                val arguments = node.argumentList?.arguments.orEmpty()
                if (arguments.size != 2) return

                val value = SageIntegerLiteralParser.parse(arguments[0].text) ?: return
                val modulus = SageIntegerLiteralParser.parse(arguments[1].text)?.takeIf { it != BigInteger.ZERO } ?: return
                val gcd = value.gcd(modulus)
                if (gcd == BigInteger.ONE) return

                holder.registerProblem(
                    node,
                    "No modular inverse exists: gcd($value, $modulus) = $gcd, not 1.",
                    ProblemHighlightType.ERROR,
                )
            }
        }

    private companion object {
        const val INVERSE_MOD = "inverse_mod"
    }
}
