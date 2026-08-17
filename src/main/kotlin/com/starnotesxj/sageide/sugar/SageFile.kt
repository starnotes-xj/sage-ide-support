package com.starnotesxj.sageide.sugar

import com.intellij.openapi.fileTypes.FileType
import com.intellij.psi.FileViewProvider
import com.jetbrains.python.psi.impl.PyFileImpl
import javax.swing.Icon

/**
 * The Sage dialect file PSI.
 *
 * PyCharm 2026.1's `PyFileImpl` unconditionally reports the Python identity on
 * two virtual methods (both verified against the release jar):
 *
 * - `getIcon()` returns the Python icon, and the project view calls
 *   `PsiFileNode.computeIcon -> value.getIcon()`, so a Sage file — whose PSI is
 *   a PyFile — showed the Python icon in the tree even though its file type
 *   (SageFileType) and the editor tab carry the Sage icon.  The IconProvider /
 *   FileIconProvider chains never run on this path because `getIcon()` is a
 *   virtual override that short-circuits them.
 * - `getFileType()` returns `PythonFileType.INSTANCE` (release-only override
 *   family, same as getIcon).  This is not cosmetic: the postfix completion
 *   machinery (`PostfixLiveTemplate.copyFile`) derives the language for the
 *   template-applicability COPY file from `file.getFileType()` via
 *   `LanguageUtil.getLanguageForPsi` — with the Python answer, the copy is
 *   created by the Python parser definition as a plain PyFile, so every
 *   `context.containingFile is SageFile` gate in our templates' isApplicable
 *   failed and the Sage postfix set never appeared (v1.6.0 popup bug).
 *
 * Overriding both here — the file is created from
 * [com.starnotesxj.sageide.parser.SageParserDefinition.createFile] — restores
 * the Sage identity on the PSI-file chain.  This mirrors the upstream pattern
 * for the `.pyi` dialect: `PyiFile` extends `PyFileImpl` and overrides
 * `getFileType()` to `PyiFileType`.  `getLanguage()` is deliberately left as
 * Python (PyFileImpl's default) — the plugin's design relies on `.sage`
 * reading as Python at the PSI level everywhere except where Sage identity is
 * required.
 */
class SageFile(viewProvider: FileViewProvider) : PyFileImpl(viewProvider) {

    override fun getIcon(flags: Int): Icon = SageIcons.SAGE

    override fun getFileType(): FileType = SageFileType.INSTANCE
}
