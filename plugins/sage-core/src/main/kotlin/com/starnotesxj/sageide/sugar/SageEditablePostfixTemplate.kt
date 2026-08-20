package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.impl.TemplateImpl
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.openapi.editor.Document
import com.intellij.psi.PsiElement
import com.jetbrains.python.codeInsight.postfix.PyEditablePostfixTemplate
import com.jetbrains.python.codeInsight.postfix.PyPostfixTemplateExpressionCondition

/**
 * A user-created Sage postfix template.
 *
 * Reuses PyCharm's editable-Python-template machinery
 * ([PyEditablePostfixTemplate]: live-template body, expression-type
 * conditions, topmost-expression option, persistence round trip) and adds the
 * same SageFile gate the built-in Sage templates carry — a user-created
 * template applies in `.sage` files only, never leaking into plain `.py`.
 */
@Suppress("PostfixTemplateDescriptionNotFound")
class SageEditablePostfixTemplate(
    templateId: String,
    templateName: String,
    liveTemplate: TemplateImpl,
    example: String,
    conditions: Set<PyPostfixTemplateExpressionCondition?>,
    topmost: Boolean,
    provider: PostfixTemplateProvider,
    builtin: Boolean,
) : PyEditablePostfixTemplate(
    templateId, templateName, liveTemplate, example, conditions, topmost, provider, builtin,
) {

    override fun getExpressions(context: PsiElement, document: Document, offset: Int): List<PsiElement> {
        if (context.containingFile !is SageFile) return emptyList()
        return super.getExpressions(context, document, offset)
    }
}
