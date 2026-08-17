package com.starnotesxj.sageide.sugar

import com.intellij.lang.Language
import com.intellij.lang.MetaLanguage
import com.jetbrains.python.PythonLanguage

/**
 * Meta-language whose criterion is "any Python-family language" (Python and
 * its dialects — Sage included).
 *
 * The Sage postfix provider is registered under this meta-language's ID
 * (`SageMathPostfix`, see plugin.xml) instead of a concrete language.
 * `LanguageExtension` lookups then consult meta-languages: a lookup for
 * Python also collects extensions keyed with every meta-language ID that
 * matches Python (see `LanguageExtension.buildExtensions`).  That gives us
 * BOTH:
 *
 * - the completion popup still sees the provider in `.sage` files — their
 *   `PsiUtilCore.getLanguageAtOffset` resolves to PYTHON (element types
 *   hardcode the Python language), so the provider must be collectable from a
 *   Python-keyed lookup;
 * - the postfix settings tree groups the provider under its own top-level
 *   "SageMathPostfix" node (the tree groups by the extension's `language`
 *   key) instead of nesting it under Python.
 *
 * The ID is deliberately a distinct string (not `Sage`, not `Python`, not
 * `SageMath`): the only extensions any language extension point ever picks up
 * through this meta-language are the ones THIS plugin registers under
 * `SageMathPostfix` — zero effect on other language-keyed extension points —
 * and it cannot collide with languages declared by other plugins (e.g. the
 * JetBrains SageMath marketplace plugin's `SageMath` language).
 *
 * Registered directly on the (deprecated) `com.intellij.metaLanguage` EP —
 * the modern `MetaLanguageProvider` replacement does not exist in PyCharm
 * 2026.1, so this is the only registration form that verifies Compatible
 * across 261–263.  The EP instantiates this class once per plugin load, so
 * the `Language` constructor's one-instance-per-class rule is satisfied.
 */
class SagePostfixLanguage : MetaLanguage("SageMathPostfix") {

    override fun matchesLanguage(language: Language): Boolean =
        language.isKindOf(PythonLanguage.INSTANCE)
}
