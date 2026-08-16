package com.starnotesxj.sageide.run

import com.intellij.execution.lineMarker.RunLineMarkerContributor
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageIcons

/**
 * Shows the run gutter icon on Sage files, launching the Sage run
 * configuration instead of the Python one.
 */
class SageRunLineMarkerContributor : RunLineMarkerContributor() {

    override fun getInfo(element: PsiElement): Info? {
        val file = element as? PsiFile ?: return null
        if (!SageFileUtils.isSageFile(file.virtualFile)) return null
        if (element !== file.firstChild) return null
        return Info(SageIcons.SAGE, arrayOf(RunSageFileAction()), { "Run Sage script" })
    }
}
