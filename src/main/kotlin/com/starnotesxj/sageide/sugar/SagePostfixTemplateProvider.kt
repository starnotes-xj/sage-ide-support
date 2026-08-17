package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplate
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.StringBasedPostfixTemplate
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiFile
import com.jetbrains.python.codeInsight.postfix.PyCallWrapPostfixTemplate
import com.jetbrains.python.codeInsight.postfix.PyPostfixTemplateProvider

/**
 * SageMath postfix templates for `.sage` files.
 *
 * PyCharm ships postfix completion (`.if`, `.return`, ...) for Python, but the
 * template list is plugin-provided only — users cannot add their own in the
 * settings UI.  This provider adds the Sage coercion/wrapper family:
 *
 * - `.ZZ` / `.QQ` / `.RR` / `.CC` / `.SR` — ring coercions (`ZZ(expr)`, ...)
 * - `.Integer` — exact integer coercion
 * - `.N` — numeric evaluation
 * - `.factor` / `.show` — factorisation / pretty display
 * - `.vector` / `.matrix` — container coercions
 * - CTF number theory: `.euler_phi`, `.carmichael_lambda`, `.divisors`,
 *   `.number_of_divisors`, `.prime_factors`, `.squarefree_part`,
 *   `.next_prime`, `.random_prime`, `.primitive_root`, `.factorial`,
 *   `.numerator`, `.denominator`, `.continued_fraction`,
 *   `.cyclotomic_polynomial`, `.sage_eval`
 * - bytes <-> int (fixed-argument patterns): `.b2i` ->
 *   `int.from_bytes(expr, "big")`, `.i2b` -> `int(expr).to_bytes(<len>, "big")`
 *
 * Every referenced name lives in the implicit `sage.all` namespace (or is a
 * Python builtin), so expansions are valid in `.sage` files without any
 * import — the same guarantee the [SageReferenceResolveProvider] gives to
 * references.
 *
 * The registration extension point is a `LanguageExtensionPoint`, which
 * resolves to ONE provider per language and falls back to the base language:
 * registering a Sage provider without re-exporting Python's templates would
 * SHADOW the Python built-in set for the Sage dialect.  Hence this provider
 * returns the Python provider's templates plus the Sage additions.
 */
class SagePostfixTemplateProvider : PostfixTemplateProvider {

    private val sageTemplates: Set<PostfixTemplate> = buildSet {
        for (name in SAGE_WRAPPERS) {
            add(PyCallWrapPostfixTemplate(name, this@SagePostfixTemplateProvider))
        }
        add(
            SageFixedPostfixTemplate(
                name = "int.from_bytes(expr, 'big')",
                key = "b2i",
                example = "int.from_bytes(expr, 'big')",
                templateText = "int.from_bytes(${StringBasedPostfixTemplate.EXPR}, \"big\")\$END\$",
                provider = this@SagePostfixTemplateProvider,
            ),
        )
        add(
            SageFixedPostfixTemplate(
                name = "int(expr).to_bytes(len, 'big')",
                key = "i2b",
                example = "int(expr).to_bytes(len, 'big')",
                templateText = "int(${StringBasedPostfixTemplate.EXPR}).to_bytes(\$END\$, \"big\")",
                provider = this@SagePostfixTemplateProvider,
            ),
        )
    }

    override fun getId(): String = "sagePostfixTemplates"

    override fun getPresentableName(): String = "SageMath"

    override fun getTemplates(): Set<PostfixTemplate> =
        PyPostfixTemplateProvider().getTemplates() + sageTemplates

    override fun isTerminalSymbol(currentChar: Char): Boolean =
        currentChar == '.' || currentChar == '!'

    override fun preExpand(file: PsiFile, editor: Editor) = Unit

    override fun afterExpand(file: PsiFile, editor: Editor) = Unit

    override fun preCheck(copyFile: PsiFile, realEditor: Editor, currentOffset: Int): PsiFile =
        copyFile

    companion object {
        private val SAGE_WRAPPERS = listOf(
            // Coercions / basics
            "ZZ", "QQ", "RR", "CC", "SR", "Integer", "N",
            "factor", "show", "vector", "matrix",
            // CTF number theory (all live in sage.all)
            "euler_phi", "carmichael_lambda", "divisors", "number_of_divisors",
            "prime_factors", "squarefree_part", "next_prime", "random_prime",
            "primitive_root", "factorial", "numerator", "denominator",
            "continued_fraction", "cyclotomic_polynomial", "sage_eval",
        )
    }
}
