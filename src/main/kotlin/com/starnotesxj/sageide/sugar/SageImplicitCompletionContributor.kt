package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.completion.CompletionContributor
import com.intellij.codeInsight.completion.CompletionParameters
import com.intellij.codeInsight.completion.CompletionProvider
import com.intellij.codeInsight.completion.CompletionResultSet
import com.intellij.codeInsight.completion.CompletionType
import com.intellij.codeInsight.completion.InsertHandler
import com.intellij.codeInsight.completion.InsertionContext
import com.intellij.codeInsight.lookup.LookupElement
import com.intellij.codeInsight.lookup.LookupElementBuilder
import com.intellij.codeInsight.lookup.LookupElementPresentation
import com.intellij.openapi.diagnostic.Logger
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
 * The entry presentation mirrors the one PROVEN pipeline in the Python
 * plugin — `CompletionVariantsProcessor`'s builtin entries
 * (`createWithSmartPointer(name, element)` + `withIcon` + `withTypeText`):
 * those show their gray tail (e.g. `ModuleNotFoundError — builtins`) in the
 * same popup, so every other presentation route is avoided here.  Callable
 * names (functions, classes, factories like ZZ/RR/CC, symbolic function
 * wrappers — [SageStubIndex.isCallableDeclaration]) insert `()` with the
 * caret inside.
 *
 * The entries insert the bare name — no `from sage.all import X`: the `sage`
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
                    val file = parameters.originalFile
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

                    var added = 0
                    for ((name, element) in SageStubIndex.collectSageAllDeclarations(position.project)) {
                        if (!result.prefixMatcher.prefixMatches(name)) continue
                        val validElement = element?.takeIf { it.isValid }
                        // The builtins-entry pipeline (CompletionVariantsProcessor):
                        // smart pointer + icon + single-arg withTypeText — the
                        // only presentation route proven to render its tail in
                        // this popup (ModuleNotFoundError — builtins).
                        //
                        // CRITICAL: LookupElementBuilder is IMMUTABLE — every
                        // with* method returns a NEW builder, and dropping the
                        // return value silently strips the presentation/handler
                        // (v1.7.6 shipped exactly that bug: the popup entries
                        // had no typeText and no insert handler, so neither the
                        // sage.all tail nor the () insertion ever appeared).
                        var builder = if (validElement != null) {
                            LookupElementBuilder.createWithSmartPointer(name, validElement)
                        } else {
                            LookupElementBuilder.create(name)
                        }
                        validElement?.getIcon(0)?.let { builder = builder.withIcon(it) }
                        builder = builder.withTypeText("sage.all")
                        val callable = SageStubIndex.isCallableDeclaration(position.project, name, validElement)
                        if (callable) {
                            builder = builder.withInsertHandler(SageParensInsertHandler)
                        }
                        result.addElement(builder)
                        added++
                        if (added <= 6) {
                            val presentation = LookupElementPresentation.renderElement(builder)
                            LOG.warn(
                                "Sage completion entry: '$name' callable=$callable psi=${validElement?.javaClass?.simpleName} pres=$presentation",
                            )
                        }
                    }
                    if (added > 0 && added <= 30 || prefix.length <= 2) {
                        LOG.warn(
                            "Sage completion: prefix='$prefix' in ${file.name} -> added $added sage.all entries",
                        )
                    }
                }
            },
        )
    }

    /**
     * Unconditional `()` insertion (caret inside) — unlike
     * `ParenthesesInsertHandler` it does not consult the editor's
     * "insert parentheses on completion" setting, because the user asked for
     * parens explicitly.
     */
    private object SageParensInsertHandler : InsertHandler<LookupElement> {
        override fun handleInsert(context: InsertionContext, item: LookupElement) {
            val editor = context.editor
            val document = editor.document
            val offset = context.tailOffset
            if (offset < document.textLength && document.charsSequence[offset] == '(') {
                // The user already typed '('; just place the caret after it.
                editor.caretModel.moveToOffset(offset + 1)
                return
            }
            document.insertString(offset, "()")
            editor.caretModel.moveToOffset(offset + 1)
        }
    }

    companion object {
        private val LOG = Logger.getInstance(SageImplicitCompletionContributor::class.java)
    }
}
