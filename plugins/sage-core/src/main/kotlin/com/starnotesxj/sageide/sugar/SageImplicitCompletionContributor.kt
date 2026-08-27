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
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.DumbService
import com.intellij.patterns.PlatformPatterns
import com.intellij.patterns.StandardPatterns
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.util.ProcessingContext
import com.starnotesxj.sageide.completion.SageApiClassMembersProvider
import com.starnotesxj.sageide.completion.SageApiIndexService
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
            PlatformPatterns.psiElement(),
            object : CompletionProvider<CompletionParameters>() {
                override fun addCompletions(
                    parameters: CompletionParameters,
                    context: ProcessingContext,
                    result: CompletionResultSet,
                ) {
                    val file = parameters.originalFile
                    if (!SageFileUtils.isSageFile(file)) return
                    val position = parameters.position
                    // At the end of an identifier PyCharm may expose the file/leaf
                    // at the caret rather than the reference itself. Probe the
                    // current and preceding offsets so qualified completion works
                    // for both B.det<caret> and an in-token caret.
                    val probeOffset = (parameters.offset - 1)
                        .coerceIn(0, (file.textLength - 1).coerceAtLeast(0))
                    val reference = sequenceOf(
                        PsiTreeUtil.getParentOfType(position, PyReferenceExpression::class.java),
                        PsiTreeUtil.getParentOfType(
                            PsiTreeUtil.prevVisibleLeaf(position),
                            PyReferenceExpression::class.java,
                        ),
                        // Completion may place the caret on a file/error leaf at EOF;
                        // recover a reference from the current insertion boundary.
                        file.findElementAt(probeOffset)
                            ?.let { PsiTreeUtil.getParentOfType(it, PyReferenceExpression::class.java) },
                    ).filterNotNull().firstOrNull()
                    // Completion may expose a file/error leaf at EOF. If the
                    // direct PSI walk did not find the member reference, use the
                    // nearest qualified reference that begins before the completion
                    // offset; this mirrors the reference selected by Python's own
                    // qualified completion path.
                    val completionReference = reference ?: PsiTreeUtil
                        .collectElementsOfType(file, PyReferenceExpression::class.java)
                        .asSequence()
                        .filter { candidate ->
                            candidate.isQualified &&
                                candidate.textRange.startOffset <= parameters.offset &&
                                candidate.textRange.endOffset >= parameters.offset - 1
                        }
                        .maxByOrNull { it.textRange.startOffset }
                    // A caret in a newly typed bare identifier can have no
                    // reference PSI yet. The external index must still supply
                    // root candidates; only qualified/member cases require a
                    // resolved reference and type.
                    if (completionReference != null && completionReference is PyTargetExpression) return
                    if (PsiTreeUtil.getParentOfType(position, PyImportStatementBase::class.java) != null) return

                    if (completionReference?.isQualified == true) {
                        val qualifier = completionReference.qualifier ?: return
                        val typeContext = com.jetbrains.python.psi.types.TypeEvalContext.codeCompletion(
                            position.project,
                            file,
                        )
                        val qualifierType = (typeContext.getType(qualifier)
                            // Completion's lightweight context can omit a
                            // project-local type-provider answer for a target
                            // assigned from an unannotated parameter.  Retry in
                            // the normal analysis context before giving up; the
                            // returned class is still the same active .pyi PSI
                            // object checked by the type provider, not an
                            // index-only or structural approximation.
                            ?: com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(
                                position.project,
                                file,
                            ).getType(qualifier))
                            as? com.jetbrains.python.psi.types.PyClassType
                        if (qualifierType != null) {
                            // Delegate qualified member completion to the same
                            // Python type path used by PyQualifiedReference. It
                            // carries the real completion context and invokes
                            // every registered PyClassMembersProvider, including
                            // Sage indexed members.
                            val variants = qualifierType.getCompletionVariants(
                                // An unfinished `receiver.` reference has no
                                // PSI name yet.  PyClassType expects an empty
                                // prefix for that normal completion state;
                                // passing null suppresses every native and
                                // index-backed member variant.
                                completionReference.referencedName.orEmpty(),
                                completionReference,
                                ProcessingContext(),
                            )
                            val referenceRange = completionReference.reference.rangeInElement
                            val offsetInElement =
                                (parameters.offset - completionReference.textRange.startOffset)
                                    .coerceIn(referenceRange.startOffset, referenceRange.endOffset)
                            val memberPrefix = completionReference.text.substring(
                                referenceRange.startOffset,
                                offsetInElement,
                            )
                            val memberResult = result.withPrefixMatcher(memberPrefix)
                            val emittedNames = linkedSetOf<String>()
                            for (variant in variants) {
                                if (variant is LookupElement) {
                                    emittedNames += variant.lookupString
                                    memberResult.addElement(variant)
                                }
                            }
                            // PyClassType's variant builder can be empty for an
                            // incomplete `receiver.` PSI node, even though the
                            // receiver has already been proven to be a concrete
                            // active Sage stub class.  Rehydrate the missing
                            // native methods and indexed members directly from
                            // that same class identity.  This preserves exact
                            // class ownership (including inheritance) and never
                            // falls back to a common base or a name whitelist.
                            val memberContext = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(
                                position.project,
                                file,
                            )
                            for (method in qualifierType.pyClass.getMethodsInherited(memberContext)) {
                                val methodName = method.name ?: continue
                                if (!emittedNames.add(methodName)) continue
                                var builder = LookupElementBuilder.createWithSmartPointer(methodName, method)
                                method.getIcon(0)?.let { builder = builder.withIcon(it) }
                                memberResult.addElement(builder)
                            }
                            val owner = SageStubIndex.canonicalQualifiedName(qualifierType.pyClass).orEmpty()
                            for (member in SageApiClassMembersProvider()
                                .getMembers(qualifierType, completionReference, memberContext)) {
                                if (!emittedNames.add(member.name)) continue
                                var builder = LookupElementBuilder.create(member.name)
                                member.icon?.let { builder = builder.withIcon(it) }
                                if (owner.isNotBlank()) builder = builder.withTypeText(owner)
                                memberResult.addElement(builder)
                            }
                        }
                        return
                    }

                    // Explicit sage.all imports already participate in Python's
                    // normal root completion. Keep this contributor additive there,
                    // while qualified members above still use the Sage provider.
                    if (SageFileUtils.hasExplicitSageAllImport(file)) return

                    val prefix = result.prefixMatcher.prefix
                    if (prefix.isEmpty()) {
                        // With an empty prefix, let the platform decide whether
                        // to show the large namespace; a subsequent typed prefix
                        // invocation still applies the same exact matcher.
                        result.restartCompletionOnPrefixChange(StandardPatterns.string().longerThan(0))
                    }
                    // Cold cache would need the stub indexes, which are
                    // unavailable while the IDE is indexing. The authoritative
                    // external namespace remains usable during that phase; skip
                    // only the optional PSI-backed candidates.
                    val emittedNames = linkedSetOf<String>()
                    if (!DumbService.isDumb(position.project)) {
                        for ((name, element) in SageStubIndex.collectSageAllDeclarations(position.project)) {
                        if (!result.prefixMatcher.prefixMatches(name)) continue
                        emittedNames += name
                        val validElement = element?.takeIf { it.isValid }
                        // From-import aliases (factor, ECM, Integer, ...) are
                        // followed to their REAL declaration so the entry
                        // carries the real icon (red f for functions) and
                        // documentation target.
                        val entryTarget = SageStubIndex.resolveEntryTarget(position.project, name, validElement)
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
                        var builder = if (entryTarget != null) {
                            LookupElementBuilder.createWithSmartPointer(name, entryTarget)
                        } else {
                            LookupElementBuilder.create(name)
                        }
                        entryTarget?.getIcon(0)?.let { builder = builder.withIcon(it) }
                        builder = builder.withTypeText("sage.all")
                        val callable = SageStubIndex.isCallableDeclaration(position.project, name, validElement)
                        if (callable) {
                            builder = builder.withInsertHandler(SageParensInsertHandler)
                        }
                        result.addElement(builder)
                        }
                    }

                    // The stub PSI index gives rich navigation when stubs are attached,
                    // but it may expose only a subset of a configured full artifact.
                    // Add the remaining immutable `sage.all` namespace identities from
                    // the validated external index without fabricating PSI targets.
                    for (entry in SageApiIndexService.getInstance().query()?.namespaceEntries("sage.all").orEmpty()) {
                        val name = entry.qualifiedName.substringAfterLast('.')
                        if (name in emittedNames || !result.prefixMatcher.prefixMatches(name)) continue
                        var builder = LookupElementBuilder.create(name).withTypeText("sage.all")
                        val callable = entry.kind == com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.FUNCTION ||
                            entry.kind == com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.CLASS ||
                            (entry.kind == com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.ALIAS &&
                                SageApiIndexService.getInstance().query()?.resolve(entry.aliases.firstOrNull().orEmpty())?.kind in
                                    setOf(
                                        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.FUNCTION,
                                        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.CLASS,
                                    ))
                        if (callable) {
                            builder = builder.withInsertHandler(SageParensInsertHandler)
                        }
                        result.addElement(builder)
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
}
