package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.StringBasedPostfixTemplate
import com.intellij.psi.PsiElement
import com.jetbrains.python.codeInsight.postfix.PyPostfixUtils

/**
 * A postfix template whose expansion is a fixed call pattern with literal
 * arguments (unlike [com.jetbrains.python.codeInsight.postfix.PyCallWrapPostfixTemplate],
 * which can only produce ``name($EXPR$)``).
 *
 * Used for CTF-common conversions such as ``.b2i`` -> ``int.from_bytes(expr, "big")``
 * and ``.i2b`` -> ``int(expr).to_bytes(<caret>, "big")``.
 */
class SageFixedPostfixTemplate(
    name: String,
    key: String,
    example: String,
    private val templateText: String,
    provider: PostfixTemplateProvider,
) : StringBasedPostfixTemplate(
    name,
    key,
    example,
    PyPostfixUtils.selectorAllExpressionsWithCurrentOffset(),
    provider,
) {
    override fun getTemplateString(element: PsiElement): String = templateText
}
