package com.starnotesxj.sageide.sugar

import com.intellij.psi.FileViewProvider
import com.jetbrains.python.psi.impl.PyFileImpl
import javax.swing.Icon

/**
 * The Sage dialect file PSI.
 *
 * PyCharm 2026.1's `PyFileImpl.getIcon()` unconditionally returns the Python
 * icon (verified by decompiling the release jar), and the project view calls
 * `PsiFileNode.computeIcon -> value.getIcon()`, so a Sage file — whose PSI is
 * a PyFile — showed the Python icon in the tree even though its file type
 * (SageFileType) and the editor tab carry the Sage icon.  The IconProvider /
 * FileIconProvider chains never run on this path because `getIcon()` is a
 * virtual override that short-circuits them.
 *
 * Overriding `getIcon()` here — the file is created from
 * [com.starnotesxj.sageide.parser.SageParserDefinition.createFile] — restores
 * the Sage icon in every view that uses the PSI-element chain.
 */
class SageFile(viewProvider: FileViewProvider) : PyFileImpl(viewProvider) {

    override fun getIcon(flags: Int): Icon = SageIcons.SAGE
}
