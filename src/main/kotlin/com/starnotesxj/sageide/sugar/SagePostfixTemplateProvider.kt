package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplate
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplatesUtils
import com.intellij.codeInsight.template.postfix.templates.editable.PostfixTemplateEditor
import com.intellij.codeInsight.template.postfix.templates.editable.PostfixTemplateExpressionCondition
import com.intellij.openapi.editor.Editor
import com.intellij.psi.PsiFile
import com.jetbrains.python.codeInsight.postfix.PyPostfixTemplateExpressionCondition
import org.jdom.Element

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
 * **Registration key is the `SageMathPostfix` meta-language, not `Python`**
 * (see plugin.xml + [SagePostfixLanguage]): every Python PSI element type
 * reports `PythonLanguage` (PyElementType hardcodes the Python file type's
 * language), so `PsiUtilCore.getLanguageAtOffset` resolves `.sage` files as
 * PYTHON and the completion machinery collects postfix providers via
 * `allForLanguage(Python)` — a provider registered for a concrete language
 * other than Python is never consulted.  Registering under a meta-language
 * that matches the Python family makes the popup collect us for Python
 * lookups, AND the settings tree (which groups providers by their
 * registration key) shows us under our own top-level "SageMathPostfix" node
 * instead of nesting us under Python.  Each template's `isApplicable` gates
 * on the containing file being a [SageFile], so nothing leaks into plain
 * `.py` files.  The provider returns ONLY the Sage additions — Python's
 * built-in postfix set comes from PyPostfixTemplateProvider through the same
 * language collection.
 */
class SagePostfixTemplateProvider : PostfixTemplateProvider {

    private val sageTemplates: Set<PostfixTemplate> = buildSet {
        for (name in SAGE_WRAPPERS) {
            add(SageCallWrapPostfixTemplate(name, this@SagePostfixTemplateProvider))
        }
        add(SageBytesToIntPostfixTemplate(this@SagePostfixTemplateProvider))
        add(SageIntToBytesPostfixTemplate(this@SagePostfixTemplateProvider))
    }

    override fun getId(): String = "sagePostfixTemplates"

    override fun getPresentableName(): String = "SageMath"

    override fun getTemplates(): Set<PostfixTemplate> = sageTemplates

    override fun isTerminalSymbol(currentChar: Char): Boolean =
        currentChar == '.' || currentChar == '!'

    override fun preExpand(file: PsiFile, editor: Editor) = Unit

    override fun afterExpand(file: PsiFile, editor: Editor) = Unit

    override fun preCheck(copyFile: PsiFile, realEditor: Editor, currentOffset: Int): PsiFile =
        copyFile

    /**
     * Supports creating new Sage postfix templates in the settings UI (the
     * "+" button).  Mirrors PyPostfixTemplateProvider: the editor handles the
     * live-template body and the Python expression-type conditions; the
     * produced [SageEditablePostfixTemplate] carries the SageFile gate like
     * the built-ins.
     */
    override fun createEditor(templateToEdit: PostfixTemplate?): PostfixTemplateEditor? =
        if (templateToEdit == null || templateToEdit is SageEditablePostfixTemplate) {
            SagePostfixTemplateEditor(this)
        } else {
            null
        }

    override fun readExternalTemplate(id: String, name: String, templateElement: Element): PostfixTemplate? {
        val template = PostfixTemplatesUtils.readExternalLiveTemplate(templateElement, this) ?: return null
        val conditions = PostfixTemplatesUtils.readExternalConditions(
            templateElement,
            com.intellij.util.Function { element: Element -> readCondition(element) })
        val topmost = PostfixTemplatesUtils.readExternalTopmostAttribute(templateElement)
        return SageEditablePostfixTemplate(id, name, template, "", conditions, topmost, this, false)
    }

    override fun writeExternalTemplate(template: PostfixTemplate, parentElement: Element) {
        if (template is SageEditablePostfixTemplate) {
            PostfixTemplatesUtils.writeExternalTemplate(template, parentElement)
        }
    }

    private fun readCondition(conditionElement: Element): PyPostfixTemplateExpressionCondition? {
        val id = conditionElement.getAttributeValue(PostfixTemplateExpressionCondition.ID_ATTR)
        return if (PyPostfixTemplateExpressionCondition.PyClassCondition.ID == id) {
            PyPostfixTemplateExpressionCondition.PyClassCondition.readFrom(conditionElement)
        } else {
            PyPostfixTemplateExpressionCondition.PUBLIC_CONDITIONS[id]
        }
    }

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
