package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.StringBasedPostfixTemplate
import com.intellij.openapi.editor.Document
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.util.NlsContexts
import com.intellij.openapi.util.NlsSafe
import com.intellij.psi.PsiElement
import com.jetbrains.python.codeInsight.postfix.PyPostfixUtils

/**
 * Wraps an expression with a call to a `sage.all` function such as `ZZ`,
 * `QQ`, `factor` or `euler_phi`: `expr.ZZ` -> `ZZ(expr)`.
 *
 * This is our own class (not a reuse of
 * [com.jetbrains.python.codeInsight.postfix.PyCallWrapPostfixTemplate]) so the
 * postfix template description and before/after examples resolve from OUR
 * plugin's resources — the platform renders the settings preview from
 * `postfixTemplates/<SimpleClassName>/` and would otherwise show the Python
 * plugin's generic `expr.list` / `list(expr)` examples for every Sage key.
 *
 * The concrete templates are the per-key subclasses in
 * [com.starnotesxj.sageide.sugar.SageCallWrapPostfixTemplatesKt] — each key
 * has its own class (and therefore its own resource directory) because the
 * settings preview replaces `$key` with the DOT-PREFIXED key verbatim: a
 * shared resource with `$key` would render `expr.CC` / `.CC(expr)` (extra
 * dot in the after state).  Per-key resources hardcode the plain name.
 *
 * Templates are editable in the same way Python's built-ins are: the
 * settings tree offers a rename dialog (the default editor) and a renamed
 * built-in is persisted as a `PostfixChangedBuiltinTemplate`; the storage
 * round trip is complete (`writeExternalTemplate` / `readExternalTemplate`
 * plus the platform's builtin-fallback for body-less entries), so no
 * half-written entries can appear (the v1.5.0 corruption case).
 *
 * Variable convention: built-in templates reference the target expression as
 * `$expr$` (lowercase — the platform's `StringBasedPostfixTemplate.EXPR`
 * registration, same as PyCharm's own built-ins); user-created templates
 * created in the editor use `$EXPR$` (uppercase — the `EditablePostfixTemplate`
 * registration).  Variable lookup is case-sensitive, so each class family
 * must keep its own spelling.
 */
open class SageCallWrapPostfixTemplate(
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

    /**
     * The per-key subclasses carry only their own before/after preview
     * resources; the family description is shared here (it is not keyed by
     * the subclass resource directory).
     */
    @NlsSafe
    override fun getDescription(): @NlsContexts.DetailedDescription String = FAMILY_DESCRIPTION

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

    companion object {
        private const val FAMILY_DESCRIPTION: String =
            "<html><body>" +
            "Wraps the selected expression into the corresponding <code>sage.all</code> call " +
            "(no import needed in a <code>.sage</code> file):<br/>" +
            "<code>expr</code><b>.ZZ</b> &rarr; <code>ZZ(expr)</code>, " +
            "<code>expr</code><b>.factor</b> &rarr; <code>factor(expr)</code>, " +
            "<code>expr</code><b>.euler_phi</b> &rarr; <code>euler_phi(expr)</code>, &hellip;" +
            "</body></html>"
    }
}
