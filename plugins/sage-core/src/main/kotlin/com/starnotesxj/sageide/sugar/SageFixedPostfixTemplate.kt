package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.StringBasedPostfixTemplate
import com.intellij.openapi.editor.Document
import com.intellij.openapi.project.DumbAware
import com.intellij.psi.PsiElement
import com.jetbrains.python.codeInsight.postfix.PyPostfixUtils

/**
 * A postfix template whose expansion is a fixed call pattern with literal
 * arguments (unlike [com.jetbrains.python.codeInsight.postfix.PyCallWrapPostfixTemplate],
 * which can only produce ``name($EXPR$)``).
 *
 * Used for CTF-common conversions such as ``.b2i`` -> ``int.from_bytes(expr, "big")``
 * and ``.i2b`` -> ``int(expr).to_bytes(<caret>, "big")``.
 *
 * **The key must carry the leading dot** (`.b2i`, not `b2i`): the platform
 * postfix machinery works with dot-prefixed keys throughout —
 * `PostfixLiveTemplate.computeTemplateKeyWithoutContextChecking` walks back
 * INCLUDING the terminal symbol (so the computed key for `m.b2i` is `.b2i`),
 * `PostfixTemplate`'s standard constructors build the key as `"." + name`, and
 * the completion prefix matcher is cloned to the dot-included key while the
 * lookup element's lookup string is the raw key.  A bare key breaks both the
 * popup matching (item dropped at `CompletionResult.wrap`) and expansion
 * (`findApplicableTemplate` key equality fails).
 *
 * Concrete templates are the subclasses ([SageBytesToIntPostfixTemplate],
 * [SageIntToBytesPostfixTemplate]), each carrying its own
 * `postfixTemplates/<SubclassName>/` description/example resources.
 *
 * Templates are editable in the same way Python's built-ins are: the
 * settings tree offers a rename dialog (the default editor); the storage
 * round trip is complete, so renamed built-ins persist as
 * `PostfixChangedBuiltinTemplate` entries without half-written data (the
 * v1.5.0 corruption case).
 */
open class SageFixedPostfixTemplate(
    name: String,
    private val key: String,
    example: String,
    private val templateText: String,
    provider: PostfixTemplateProvider,
) : StringBasedPostfixTemplate(
    name,
    key,
    example,
    PyPostfixUtils.selectorAllExpressionsWithCurrentOffset(),
    provider,
), DumbAware {

    override fun getTemplateString(element: PsiElement): String = templateText

    /**
     * The provider is registered for the Python language (see plugin.xml) so
     * the completion machinery can see it at all; gate applicability on the
     * containing file being a [SageFile] so the templates never leak into
     * plain `.py` files.  See [SageCallWrapPostfixTemplate.isApplicable] for
     * why the copy file is a SageFile since v1.6.1.
     */
    override fun isApplicable(context: PsiElement, copyDocument: Document, newOffset: Int): Boolean =
        context.containingFile is SageFile && super.isApplicable(context, copyDocument, newOffset)
}
