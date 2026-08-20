package com.starnotesxj.sageide.highlight

import com.intellij.codeInspection.LocalInspectionTool
import com.intellij.codeInspection.LocalQuickFix
import com.intellij.codeInspection.ProblemDescriptor
import com.intellij.codeInspection.ProblemHighlightType
import com.intellij.codeInspection.ProblemsHolder
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiElementVisitor
import com.jetbrains.python.PyTokenTypes
import com.jetbrains.python.psi.PyAnnotationOwner
import com.jetbrains.python.psi.PyArgumentList
import com.jetbrains.python.psi.PyAugAssignmentStatement
import com.jetbrains.python.psi.PyBinaryExpression
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyElementVisitor
import com.jetbrains.python.psi.PyExpression
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyStatement

/**
 * The one operator where Sage syntax silently changes Python semantics:
 * in `.sage` files `^` is **exponentiation** (the preparser rewrites it to
 * `**`), so Python-style bitwise XOR written as `x ^ y` becomes `x ** y`.
 *
 * Typical CTF failure: `bytes(x ^ y for x, y in zip(a, b))` runs as
 * `x ** y` and dies with `ValueError: bytes must be in range(0, 256)`.
 * Sage's XOR spelling is `^^` (preparsed back to `^`).
 *
 * Since v1.6.0 the Sage lexer remaps carets to the preparse semantics, so
 * `^` parses as a power (EXP), `^=` as power assignment (EXPEQ), `^^` as
 * XOR and `^^=` as XOR assignment (XOREQ) — none of them are syntax errors
 * any more.  This inspection therefore flags the **semantic** misuse only:
 * an EXP token whose text is `^` (or an EXPEQ token whose text is `^=`)
 * where a Python-XOR intent is unambiguous — a `bytes`-typed operand
 * (b"..." literal, `bytes(...)`, `bytes.fromhex`, `int.to_bytes` /
 * `int.from_bytes`, a parameter or target annotated `bytes`/`bytearray`)
 * or a `^` that feeds directly into a `bytes(...)` call.  Sage power math
 * (`e^254`, `2^8`) is never flagged.
 */
class SageXorInspection : LocalInspectionTool() {

    override fun buildVisitor(holder: ProblemsHolder, isOnTheFly: Boolean): PsiElementVisitor =
        object : PyElementVisitor() {
            override fun visitPyBinaryExpression(node: PyBinaryExpression) {
                // A `^` power (EXP with text "^"); genuine `**` is never flagged.
                val operatorNode = node.node.findChildByType(PyTokenTypes.EXP)
                    ?.takeIf { it.text == "^" } ?: return
                if (!isBytesContext(node)) return
                holder.registerProblem(
                    operatorNode.psi,
                    "In Sage, ^ is exponentiation (preparsed to **), not XOR. Use ^^ for bitwise XOR.",
                    ProblemHighlightType.ERROR,
                    ReplaceCaretWithDoubleCaret,
                )
            }

            override fun visitPyAugAssignmentStatement(node: PyAugAssignmentStatement) {
                // A `^=` power assignment (EXPEQ with text "^="); `**=` is not flagged.
                val operatorNode = node.node.findChildByType(PyTokenTypes.EXPEQ)
                    ?.takeIf { it.text == "^=" } ?: return
                // Version-safe target access: PyAugAssignmentStatement.getAssignmentTarget()
                // only exists since 2026.2 (plugin verifier: NoSuchMethodError on
                // 2026.1.4).  Read the target as the first expression child of the
                // AST node instead; the operator token is not a PyExpression, so the
                // first PyExpression child is the target.
                val target = node.node.getChildren(null).firstOrNull { it.getPsi() is PyExpression }
                    ?.getPsi() as? PyExpression
                if (!isBytesLike(target) && !isBytesLike(node.value)) return
                holder.registerProblem(
                    operatorNode.psi,
                    "In Sage, ^= is power-assignment (preparsed to **=), not XOR. Use ^^= for bitwise XOR.",
                    ProblemHighlightType.ERROR,
                    ReplaceCaretEqWithDoubleCaretEq,
                )
            }
        }

    /** A `^` with unambiguous Python-XOR intent (bytes operand or feeding bytes()). */
    private fun isBytesContext(node: PyBinaryExpression): Boolean {
        if (isBytesLike(node.leftExpression) || isBytesLike(node.rightExpression)) return true
        var parent: PsiElement? = node.parent
        while (parent != null && parent !is PyArgumentList) {
            if (parent is PyStatement) return false // never walk across statements
            parent = parent.parent
        }
        val call = parent?.parent as? PyCallExpression ?: return false
        return call.callee?.text == "bytes"
    }

    private fun isBytesLike(expr: PyExpression?): Boolean {
        if (expr == null) return false
        val head = expr.text.trimStart().take(3).lowercase()
        if (
            head.startsWith("b\"") || head.startsWith("b'") ||
            head.startsWith("br\"") || head.startsWith("br'") ||
            head.startsWith("rb\"") || head.startsWith("rb'")
        ) {
            return true
        }
        if (expr is PyCallExpression) {
            when (expr.callee?.text) {
                "bytes", "bytes.fromhex", "int.to_bytes", "int.from_bytes" -> return true
            }
        }
        if (expr is PyReferenceExpression) {
            val resolved = expr.reference.resolve()
            if (resolved is PyAnnotationOwner) {
                val annotation = resolved.annotation?.text?.trim()
                if (annotation == "bytes" || annotation == "bytearray") return true
            }
        }
        return false
    }

    private object ReplaceCaretWithDoubleCaret : LocalQuickFix {
        override fun getFamilyName(): String = "Replace ^ with ^^"

        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val operator = descriptor.psiElement
            val document = PsiDocumentManager.getInstance(project)
                .getDocument(operator.containingFile) ?: return
            val range = operator.textRange
            document.replaceString(range.startOffset, range.endOffset, "^^")
        }
    }

    private object ReplaceCaretEqWithDoubleCaretEq : LocalQuickFix {
        override fun getFamilyName(): String = "Replace ^= with ^^="

        override fun applyFix(project: Project, descriptor: ProblemDescriptor) {
            val operator = descriptor.psiElement
            val document = PsiDocumentManager.getInstance(project)
                .getDocument(operator.containingFile) ?: return
            val range = operator.textRange
            document.replaceString(range.startOffset, range.endOffset, "^^=")
        }
    }
}
