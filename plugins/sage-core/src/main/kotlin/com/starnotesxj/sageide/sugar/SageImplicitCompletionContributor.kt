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
import com.intellij.icons.AllIcons
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.DumbService
import com.intellij.patterns.PlatformPatterns
import com.intellij.patterns.StandardPatterns
import com.intellij.psi.PsiComment
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.psi.PsiFile
import com.intellij.util.ProcessingContext
import com.starnotesxj.sageide.completion.SageApiClassMembersProvider
import com.starnotesxj.sageide.completion.SageApiIndexService
import com.starnotesxj.sageide.type.SageIndexedTypeResolver
import com.starnotesxj.sageide.type.SageTypeProvider
import com.jetbrains.python.psi.PyImportStatementBase
import com.jetbrains.python.psi.PyExpression
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyStringLiteralExpression
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyAnyType
import com.jetbrains.python.psi.types.PyUnionType
import javax.swing.Icon

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
        val provider = object : CompletionProvider<CompletionParameters>() {
                override fun addCompletions(
                    parameters: CompletionParameters,
                    context: ProcessingContext,
                    result: CompletionResultSet,
                ) {
                    val file = parameters.originalFile
                    if (!SageFileUtils.isSageFile(file)) return
                    val position = parameters.position
                    // The implicit Sage namespace is not relevant inside a
                    // string or comment. Returning before any PSI/index work
                    // also prevents automatic completion from filling prose
                    // and reduces needless daemon work while typing literals.
                    if (PsiTreeUtil.getParentOfType(position, PyStringLiteralExpression::class.java) != null) return
                    if (PsiTreeUtil.getParentOfType(position, PsiComment::class.java) != null) return
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

                    // With an empty member prefix (`c.<caret>`), Python PSI
                    // frequently keeps only the receiver reference and the
                    // dot token; there is no qualified PyReferenceExpression
                    // yet. Recover that receiver explicitly so completion
                    // does not fall through to the implicit sage.all root
                    // namespace (which is why the popup previously showed
                    // only entries such as `test.c`).
                    val incompleteMemberQualifier = findIncompleteMemberQualifier(file, parameters.offset)
                    val memberCompletion = completionReference?.isQualified == true ||
                        incompleteMemberQualifier != null
                    if (memberCompletion) {
                        val qualifier = completionReference?.qualifier ?: incompleteMemberQualifier ?: return
                        val memberLocation = completionReference ?: qualifier
                        val typeContext = com.jetbrains.python.psi.types.TypeEvalContext.codeCompletion(
                            position.project,
                            file,
                        )
                        val analysisContext = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(
                            position.project,
                            file,
                        )
                        val resolvedTarget = (qualifier.reference?.resolve() as? PyTargetExpression)
                            ?: findPreviousTargetBounded(file, qualifier)
                        val resolvedTargetType = resolvedTarget
                            ?.let { target -> SageTypeProvider().getReferenceType(target, analysisContext, completionReference)?.get() }
                        val qualifierType = sequenceOf(
                            typeContext.getType(qualifier),
                            // Completion's lightweight context can omit a
                            // project-local type-provider answer for a target
                            // assigned from an unannotated parameter.  Retry in
                            // the normal analysis context before giving up; the
                            // returned class is still the same active .pyi PSI
                            // object checked by the type provider, not an
                            // index-only or structural approximation.  Treat
                            // an explicit Any/Unknown result as omitted too:
                            // union-valued Sage factories otherwise arrive as
                            // Unknown in the lightweight completion context.
                            analysisContext.getType(qualifier),
                            // A completion PSI reference can be created before
                            // Python's lightweight context has refreshed the
                            // target.  Ask the Sage target provider directly as
                            // a final, still exact, retry; this is especially
                            // important for finite factory unions.
                            resolvedTargetType,
                        ).firstOrNull { it != null && it != PyAnyType.Any && it != PyAnyType.Unknown }
                        val memberPrefix = if (completionReference?.isQualified == true) {
                            val referenceRange = completionReference.reference.rangeInElement
                            val offsetInElement =
                                (parameters.offset - completionReference.textRange.startOffset)
                                    .coerceIn(referenceRange.startOffset, referenceRange.endOffset)
                            completionReference.text.substring(referenceRange.startOffset, offsetInElement)
                        } else {
                            ""
                        }
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
                                memberPrefix,
                                memberLocation,
                                ProcessingContext(),
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
                            val classVariants: List<PyClassType> = when (qualifierType) {
                                is PyClassType -> listOf(qualifierType)
                                is PyUnionType -> qualifierType.members.orEmpty().filterIsInstance<PyClassType>()
                                else -> emptyList()
                            }
                            for (classVariant in classVariants) {
                                for (method in classVariant.pyClass.getMethodsInherited(memberContext)) {
                                    val methodName = method.name ?: continue
                                    if (!emittedNames.add(methodName)) continue
                                    var builder = LookupElementBuilder.createWithSmartPointer(methodName, method)
                                    method.getIcon(0)?.let { builder = builder.withIcon(it) }
                                    memberResult.addElement(builder)
                                }
                                val owner = SageStubIndex.canonicalQualifiedName(classVariant.pyClass).orEmpty()
                                for (member in SageApiClassMembersProvider()
                                    .getMembers(classVariant, memberLocation, memberContext)) {
                                    if (!emittedNames.add(member.name)) continue
                                    var builder = LookupElementBuilder.create(member.name)
                                    member.icon?.let { builder = builder.withIcon(it) }
                                    if (owner.isNotBlank()) builder = builder.withTypeText(owner)
                                    memberResult.addElement(builder)
                                }
                            }
                        }

                        // A remote WSL SDK can have a valid Sage runtime while
                        // its skeleton generator has not materialized every
                        // Sage `.pyi` class in local PSI.  In that case the
                        // exact indexed return contracts still prove the
                        // receiver owners.  Query those canonical owners
                        // directly instead of falling through to Python's
                        // unrelated `test.c` symbol completion.  This is a
                        // union of concrete indexed classes, never a public
                        // base-class or name whitelist fallback.
                        // Native PSI types are already authoritative and avoid
                        // any index traversal on every completion keystroke.
                        // Run the index-only path solely for the missing-PSI
                        // case that it exists to repair.
                        val indexedOwners = if (qualifierType == null) linkedSetOf<String>().apply {
                            resolvedTarget?.let { addAll(SageIndexedTypeResolver.ownersForTarget(it)) }
                            if (isEmpty()) addAll(SageIndexedTypeResolver.ownersForExpression(qualifier))
                        } else {
                            emptySet()
                        }
                        if (indexedOwners.isNotEmpty()) {
                            val query = SageApiIndexService.getInstance().query()
                            if (query != null) {
                                // Some PyCharm 2026 PSI completion boundaries
                                // report the whole qualified text (`c.foo`)
                                // rather than the member tail.  The index query
                                // is already scoped to the receiver owner, so
                                // only the final identifier can be a member
                                // prefix.
                                val indexedMemberPrefix = memberPrefix.substringAfterLast('.')
                                val emittedNames = linkedSetOf<String>()
                                indexedOwners
                                    .asSequence()
                                    .flatMap { owner -> query.members(owner).asSequence().map { owner to it } }
                                    .filter { (_, entry) ->
                                        entry.qualifiedName.substringAfterLast('.')
                                            .let { indexedMemberPrefix.isEmpty() || it.startsWith(indexedMemberPrefix) }
                                    }
                                    .sortedWith(compareBy<Pair<String, com.starnotesxj.sagemath.sageapi.SageApiEntry>> { it.second.qualifiedName.substringAfterLast('.') }
                                        .thenBy { it.first })
                                    .forEach { (owner, entry) ->
                                        val name = entry.qualifiedName.substringAfterLast('.')
                                        if (!emittedNames.add(name)) return@forEach
                                        var builder = LookupElementBuilder.create(name).withTypeText(owner)
                                        indexedEntryIcon(entry.kind)?.let { builder = builder.withIcon(it) }
                                        if (entry.kind == com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.METHOD) {
                                            builder = builder.withInsertHandler(SageParensInsertHandler)
                                        }
                                        // Use the contributor's original result
                                        // so PyCharm keeps the completion session
                                        // and its current prefix matcher.  The
                                        // effective member prefix is applied by
                                        // the explicit contract filter above.
                                        result.addElement(builder)
                                    }
                            }
                        }
                        return
                    }

                    // Explicit sage.all imports already participate in Python's
                    // normal root completion. Keep this contributor additive there,
                    // while qualified members above still use the Sage provider.
                    if (SageFileUtils.hasExplicitSageAllImport(file)) return

                    val prefix = result.prefixMatcher.prefix
                    // The implicit sage.all namespace is large. PyCharm
                    // invokes BASIC completion automatically while a user is
                    // typing, so do not materialize root candidates for a
                    // one-character prefix. For an automatic two-character
                    // (or longer) prefix use only the immutable external
                    // index below; the richer PSI scan remains explicit-only.
                    val automaticRootCompletion = parameters.invocationCount == 0
                    if (automaticRootCompletion && prefix.length < 2) return
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
                    if (!automaticRootCompletion && !DumbService.isDumb(position.project)) {
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
                        indexedEntryIcon(entry.kind)?.let { builder = builder.withIcon(it) }
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
            }
        extend(CompletionType.BASIC, PlatformPatterns.psiElement(), provider)
        // Smart completion is an explicit user action. Reusing the same
        // provider keeps Sage contracts available for Ctrl+Shift+Space without
        // reintroducing automatic root-namespace work.
        extend(CompletionType.SMART, PlatformPatterns.psiElement(), provider)
    }

    /**
     * Resolve a previous assignment only when the normal PSI reference link
     * is unavailable. The fallback is deliberately bounded: a malformed or
     * very large file must not trigger a whole-file target scan on every
     * completion keystroke.
     */
    private fun findPreviousTargetBounded(
        file: PsiFile,
        qualifier: PyExpression,
    ): PyTargetExpression? {
        if (file.textLength > MAX_TARGET_FALLBACK_BYTES) return null
        val name = (qualifier as? PyReferenceExpression)?.referencedName ?: return null
        return PsiTreeUtil.collectElementsOfType(file, PyTargetExpression::class.java)
            .asSequence()
            .filter { target ->
                target.name == name && target.textRange.endOffset <= qualifier.textRange.startOffset
            }
            .maxByOrNull { it.textRange.startOffset }
    }

    private fun findIncompleteMemberQualifier(file: PsiFile, offset: Int): PyReferenceExpression? {
        val dot = file.findElementAt((offset - 1).coerceAtLeast(0))
        if (dot?.text != ".") return null
        val receiverLeaf = PsiTreeUtil.prevVisibleLeaf(dot) ?: return null
        return PsiTreeUtil.getParentOfType(receiverLeaf, PyReferenceExpression::class.java)
    }

    /** Keep index-only entries visually consistent with native Python PSI. */
    private fun indexedEntryIcon(kind: com.starnotesxj.sagemath.sageapi.SageApiSymbolKind): Icon? = when (kind) {
        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.CLASS -> AllIcons.Nodes.Class
        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.FUNCTION -> AllIcons.Nodes.Function
        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.METHOD -> AllIcons.Nodes.Method
        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.PROPERTY -> AllIcons.Nodes.Property
        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.CONSTANT -> AllIcons.Nodes.Constant
        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.MODULE -> AllIcons.Nodes.Module
        com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.ALIAS -> AllIcons.Nodes.Variable
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

    private val MAX_TARGET_FALLBACK_BYTES = 64 * 1024
}
