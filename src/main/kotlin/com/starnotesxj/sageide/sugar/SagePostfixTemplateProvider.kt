package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplate
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
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
 *
 * Every name lives in the implicit `sage.all` namespace, so expansions are
 * valid in `.sage` files without any import — the same guarantee the
 * [SageReferenceResolveProvider] gives to references.
 *
 * The registration extension point is a `LanguageExtensionPoint`, which
 * resolves to ONE provider per language and falls back to the base language:
 * registering a Sage provider without re-exporting Python's templates would
 * SHADOW the Python built-in set for the Sage dialect.  Hence this provider
 * returns the Python provider's templates plus the Sage additions.
 */
class SagePostfixTemplateProvider : PostfixTemplateProvider {

    private val sageTemplates: Set<PostfixTemplate> =
        SAGE_WRAPPERS.mapTo(linkedSetOf()) { PyCallWrapPostfixTemplate(it, this) }

    override fun getId(): String = "sagePostfixTemplates"

    override fun getPresentableName(): String = "SageMath"

    override fun getTemplates(): Set<PostfixTemplate> =
        PyPostfixTemplateProvider().getTemplates() + sageTemplates

    override fun isTerminalSymbol(currentChar: Char): Boolean = false

    override fun preExpand(file: PsiFile, editor: Editor) = Unit

    override fun afterExpand(file: PsiFile, editor: Editor) = Unit

    override fun preCheck(copyFile: PsiFile, realEditor: Editor, currentOffset: Int): PsiFile =
        copyFile

    companion object {
        private val SAGE_WRAPPERS = listOf(
            "ZZ", "QQ", "RR", "CC", "SR",
            "Integer", "N",
            "factor", "show",
            "vector", "matrix",
        )
    }
}
