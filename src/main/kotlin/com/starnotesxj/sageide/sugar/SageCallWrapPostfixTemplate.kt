package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.StringBasedPostfixTemplate
import com.intellij.openapi.editor.Document
import com.intellij.openapi.project.DumbAware
import com.intellij.psi.PsiElement
import com.jetbrains.python.codeInsight.postfix.PyPostfixUtils

/**
 * Wraps an expression with a call to a `sage.all` function such as `ZZ`,
 * `QQ`, `factor` or `euler_phi`: `expr.ZZ` -> `ZZ(expr)`.
 *
 * This is our own class (not a reuse of
 * [com.jetbrains.python.codeInsight.postfix.PyCallWrapPostfixTemplate]) so the
 * postfix template description and before/after examples resolve from OUR
 * plugin's resources (`postfixTemplates/SageCallWrapPostfixTemplate/`) — the
 * platform renders the settings preview from
 * `postfixTemplates/<SimpleClassName>/` and would otherwise show the Python
 * plugin's generic `expr.list` / `list(expr)` examples for every Sage key.
 *
 * Templates are deliberately NOT editable (`isEditable() = false`): editing
 * requires the provider to implement the live-template round trip, and a
 * half-written "changed builtin" entry in `postfixTemplates.xml` breaks the
 * completion popup.
 */
class SageCallWrapPostfixTemplate(
    private val function: String,
    provider: PostfixTemplateProvider,
) : StringBasedPostfixTemplate(
    function,
    "$function(expr)",
    PyPostfixUtils.selectorAllExpressionsWithCurrentOffset(),
    provider,
), DumbAware {

    override fun getTemplateString(element: PsiElement): String = "$function(\$expr\$)\$END\$"

    override fun getElementToRemove(expr: PsiElement): PsiElement = expr

    override fun shouldReformat(): Boolean = false

    override fun isEditable(): Boolean = false

    /**
     * The provider is registered for the Python language (see plugin.xml) so
     * the completion machinery can see it at all; gate applicability on the
     * containing file being a [SageFile] so the templates never leak into
     * plain `.py` files.
     *
     * The gate evaluates against the template-applicability COPY file created
     * by `PostfixLiveTemplate.copyFile`; since v1.6.1 [SageFile] reports
     * [SageFileType] from `getFileType()`, so `LanguageUtil.getLanguageForPsi`
     * resolves the copy's language to Sage and the copy is created through
     * [com.starnotesxj.sageide.parser.SageParserDefinition] as a SageFile —
     * the gate genuinely passes for `.sage` files.
     */
    override fun isApplicable(context: PsiElement, copyDocument: Document, newOffset: Int): Boolean =
        context.containingFile is SageFile && super.isApplicable(context, copyDocument, newOffset)
}
