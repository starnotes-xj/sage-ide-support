package com.starnotesxj.sageide.sugar

import com.intellij.ide.FileIconProvider
import com.intellij.ide.IconProvider
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFileSystemItem
import javax.swing.Icon

/**
 * Project view icon for Sage files.
 *
 * The editor tab and the PSI-element chains fall back to
 * `SageFileType.getIcon()`, but the project view resolves the VirtualFile
 * icon through the `fileIconProvider` chain, where a Python presentation can
 * win for Python-dialect files (Sage is a dialect of Python and SageFileType
 * extends PythonFileType).  Registering FIRST and answering only for `.sage`
 * files guarantees the Sage icon in the project view; every other file type
 * keeps its existing chain untouched.
 */
class SageFileIconProvider : FileIconProvider {
    override fun getIcon(file: VirtualFile, flags: Int, project: Project?): Icon? =
        if (SageFileUtils.isSageFile(file)) SageIcons.SAGE else null
}

/**
 * PSI-element icon for the Sage file itself (navigation popups, ...).
 * Fires only for file-system items (the Sage PsiFile), never for elements
 * inside the file, so method/class icons stay untouched.
 */
class SageElementIconProvider : IconProvider() {
    override fun getIcon(element: PsiElement, flags: Int): Icon? {
        if (element !is PsiFileSystemItem) return null
        return if (SageFileUtils.isSageFile(element.containingFile)) SageIcons.SAGE else null
    }
}
