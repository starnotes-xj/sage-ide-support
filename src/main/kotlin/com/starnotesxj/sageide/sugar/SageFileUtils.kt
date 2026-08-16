package com.starnotesxj.sageide.sugar

import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiFile

object SageFileUtils {
    const val SAGE_EXTENSION = "sage"

    @JvmStatic
    fun isSageFile(file: PsiFile?): Boolean = file?.virtualFile?.let { isSageFile(it) } == true

    @JvmStatic
    fun isSageFile(file: VirtualFile?): Boolean = file?.extension == SAGE_EXTENSION
}
