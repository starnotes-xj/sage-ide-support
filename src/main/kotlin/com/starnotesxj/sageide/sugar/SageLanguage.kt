package com.starnotesxj.sageide.sugar

import com.intellij.lang.DependentLanguage
import com.intellij.lang.Language
import com.jetbrains.python.PythonLanguage

/**
 * The Sage dialect of the Python language.
 *
 * Mirrors the PyiLanguageDialect precedent: files get their own language
 * identity ("Sage"), while every non-file PSI element keeps the Python
 * language (PyElementType hard-codes it), so all Python services —
 * completion, inspections, resolve, type inference — apply through the
 * platform's isKindOf language matching.
 */
class SageLanguage private constructor() : Language(PythonLanguage.INSTANCE, "Sage"), DependentLanguage {
    companion object {
        @JvmField
        val INSTANCE: SageLanguage = SageLanguage()
    }
}
