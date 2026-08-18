package com.starnotesxj.sageide.sugar

import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiFile
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyFromImportStatement

object SageFileUtils {
    const val SAGE_EXTENSION = "sage"

    @JvmStatic
    fun isSageFile(file: PsiFile?): Boolean = file?.virtualFile?.let { isSageFile(it) } == true

    @JvmStatic
    fun isSageFile(file: VirtualFile?): Boolean = file?.extension == SAGE_EXTENSION

    /**
     * True when the file imports the runtime-injected namespace explicitly
     * (`from sage.all import *` / `from sage.all import GF, ...`).
     *
     * The check must be PSI-based, not a text scan: a COMMENTED-OUT import
     * (`# from sage.all import *`) leaves no statement in the parse tree and
     * must NOT count — the `sage` command injects sage.all regardless, so a
     * text-scan gate would disable the implicit namespace while the file runs
     * perfectly (v1.7.2 regression).  Used by both the implicit-namespace
     * resolver and the implicit-namespace completion: with an explicit import
     * present, ordinary Python resolution/completion handles the names.
     */
    @JvmStatic
    fun hasExplicitSageAllImport(file: PsiFile): Boolean =
        PsiTreeUtil.collectElementsOfType(file, PyFromImportStatement::class.java)
            .any { it.importSource?.asQualifiedName()?.toString() == "sage.all" }
}
