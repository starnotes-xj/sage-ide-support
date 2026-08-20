package com.starnotesxj.sageide.sugar

import com.intellij.openapi.util.NlsSafe
import com.jetbrains.python.PythonFileType
import javax.swing.Icon

/**
 * A first-class file type for Sage files.
 *
 * The file type identifies `.sage` files as "Sage" (own name, own entry in the
 * File Types settings) with the Sage dialect of the Python language, so every
 * Python service — completion, inspections, type inference, refactorings —
 * applies through the dialect mechanism (see [SageLanguage]).  The Sage
 * parser additionally understands generator sugar statements.
 *
 * Note: `.sage` files therefore do not enter Python's module index
 * (PyModuleNameIndex filters on `fileType == PythonFileType.INSTANCE`); Sage
 * files are not imported as Python modules, so this loss is acceptable.
 */
class SageFileType : PythonFileType(SageLanguage.INSTANCE) {
    override fun getName(): String = "Sage"

    @NlsSafe
    override fun getDescription(): String = "Sage"

    override fun getDefaultExtension(): String = "sage"

    override fun getIcon(): Icon = SageIcons.SAGE

    companion object {
        @JvmField
        val INSTANCE: SageFileType = SageFileType()
    }
}
