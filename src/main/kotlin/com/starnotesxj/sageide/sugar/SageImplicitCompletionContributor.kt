package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.completion.CompletionContributor
import com.intellij.codeInsight.completion.CompletionParameters
import com.intellij.codeInsight.completion.CompletionProvider
import com.intellij.codeInsight.completion.CompletionResultSet
import com.intellij.codeInsight.completion.CompletionType
import com.intellij.codeInsight.completion.PrioritizedLookupElement
import com.intellij.codeInsight.lookup.LookupElementBuilder
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.DumbService
import com.intellij.patterns.PlatformPatterns
import com.intellij.patterns.StandardPatterns
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.util.ProcessingContext
import com.jetbrains.python.psi.PyImportStatementBase
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyTargetExpression

/**
 * Completes the runtime-injected `sage.all` namespace in `.sage` files that
 * have no explicit `from sage.all import ...` import.
 *
 * WHY THIS EXISTS — the v1.7.6 root cause: unqualified-name completion in
 * PyCharm is provided by the Python plugin's
 * `PyClassNameCompletionContributor` ("include importable names in basic
 * completion"), which scans `PyExportedModuleAttributeIndex` over a scope
 * that EXCLUDES every `.pyi` file (`createScope` intersects with
 * `notScope(getScopeRestrictedByFileTypes(everythingScope, PyiFileType))`)
 * and only offers names declared in real `.py` modules.  In the user's
 * conda-Sage the whole `sage` tree ships as `.pyi` stubs, so a name only
 * completes if some real `.py` module declares it:
 *
 * - `CC` — stubgen's bridge file `sage/rings/cc.py` (`CC = ComplexField()`)
 * - `QQ` — pure-Python `sage/rings/rational_field.py` (`QQ = RationalField()`)
 * - `ZZ` — pure-Python `sage/rings/finite_rings/integer_mod_ring.py`
 * - `RR` — only `sage/all.py` declares it, and the generated `sage/all.pyi`
 *   shadows that module; its stub declarations are `.pyi` → excluded
 * - `Mod` — declared nowhere but `.pyi` stubs (`def Mod(...)` in all.pyi)
 *
 * So CC/QQ/ZZ completed "by accident" while RR/Mod did not complete at all —
 * exactly the reported bug.  This contributor makes the whole injected
 * namespace complete uniformly, straight from the stub data layer
 * ([SageStubIndex.collectSageAllDeclarations], sourced from `sage/all.pyi`'s
 * `__all__` plus its top-level declarations), independent of which bridge or
 * pure-Python files happen to exist.
 *
 * The entries insert the bare name (no `from sage.all import X`): the `sage`
 * command injects the namespace at runtime, so an import is redundant in a
 * .sage file and would change the file's meaning for the plugin's
 * explicit-import gate.
 *
 * WHY language="Python": every Python PSI element type reports PythonLanguage
 * (PyElementType hardcodes PythonFileType's language), so completion
 * machinery consults contributors registered for Python even in .sage files,
 * while a contributor registered for the Sage dialect is never consulted
 * (v1.6.0 postfix-popup trap).  The provider gates on the containing file
 * being a .sage file, like every other language-keyed service in this plugin.
 */
class SageImplicitCompletionContributor : CompletionContributor(), DumbAware {

    init {
        extend(
            CompletionType.BASIC,
            PlatformPatterns.psiElement()
                .withParent(PyReferenceExpression::class.java)
                .withLanguage(com.jetbrains.python.PythonLanguage.INSTANCE),
            object : CompletionProvider<CompletionParameters>() {
                override fun addCompletions(
                    parameters: CompletionParameters,
                    context: ProcessingContext,
                    result: CompletionResultSet,
                ) {
                    val file = parameters.originalFile ?: return
                    if (!SageFileUtils.isSageFile(file)) return
                    // An explicit sage.all import means ordinary Python
                    // completion (star-import variants) already covers the
                    // namespace; only fill the implicit namespace otherwise.
                    if (SageFileUtils.hasExplicitSageAllImport(file)) return

                    val position = parameters.position
                    val reference = position.parent as? PyReferenceExpression ?: return
                    // Only unqualified names: `RR` yes, `foo.RR` no (that is
                    // member completion).  Skip assignment targets and import
                    // statements, where the reference is not a name use.
                    if (reference.isQualified || reference is PyTargetExpression) return
                    if (PsiTreeUtil.getParentOfType(position, PyImportStatementBase::class.java) != null) return

                    val prefix = result.prefixMatcher.prefix
                    if (prefix.isEmpty()) {
                        // Offer the namespace only once there is something to
                        // match — the list has ~1300 entries.
                        result.restartCompletionOnPrefixChange(StandardPatterns.string().longerThan(0))
                        return
                    }
                    // Cold cache would need the stub indexes, which are
                    // unavailable while the IDE is indexing.
                    if (DumbService.isDumb(position.project)) return

                    for ((name, element) in SageStubIndex.collectSageAllDeclarations(position.project)) {
                        if (!result.prefixMatcher.prefixMatches(name)) continue
                        val validElement = element?.takeIf { it.isValid }
                        val builder = LookupElementBuilder.create(name)
                        if (validElement != null) {
                            builder.withPsiElement(validElement)
                            validElement.getIcon(0)?.let { builder.withIcon(it) }
                        }
                        builder.withTypeText("sage.all", true)
                        result.addElement(PrioritizedLookupElement.withPriority(builder, -1.0))
                    }
                }
            },
        )
    }
}
