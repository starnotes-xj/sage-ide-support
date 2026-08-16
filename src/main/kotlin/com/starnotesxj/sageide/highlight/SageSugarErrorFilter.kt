package com.starnotesxj.sageide.highlight

import com.intellij.codeInsight.highlighting.HighlightErrorFilter
import com.intellij.psi.PsiErrorElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer

/**
 * Suppresses the red parser-error squiggles for Sage preparse-sugar statements
 * (`R.<x> = GF(2)[]` is not valid Python, so the Python parser leaves local
 * PsiErrorElements in exactly that statement).  Genuine errors elsewhere — in
 * .py files and in non-sugar parts of .sage files — keep their highlighting.
 */
class SageSugarErrorFilter : HighlightErrorFilter() {

    override fun shouldHighlightErrorElement(element: PsiErrorElement): Boolean {
        if (!SageFileUtils.isSageFile(element.containingFile)) return true
        val statement = PsiTreeUtil.getParentOfType(element, PyAssignmentStatement::class.java) ?: return true
        return !SageSugarAnalyzer.shapePredicate(statement)
    }
}
