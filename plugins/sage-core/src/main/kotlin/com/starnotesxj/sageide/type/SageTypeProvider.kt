package com.starnotesxj.sageide.type

import com.intellij.openapi.util.Key
import com.intellij.openapi.util.RecursionManager
import com.intellij.openapi.util.Ref
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.PyElementTypes
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyCallSiteExpression
import com.jetbrains.python.psi.PyCallable
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyLambdaExpression
import com.jetbrains.python.psi.PyNamedParameter
import com.jetbrains.python.psi.PyStatement
import com.jetbrains.python.psi.PyNumericLiteralExpression
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.impl.PyBuiltinCache
import com.jetbrains.python.psi.types.PyCallableType
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyClassTypeImpl
import com.jetbrains.python.psi.types.PyTupleType
import com.jetbrains.python.psi.types.PyType
import com.jetbrains.python.psi.types.PyTypeProviderBase
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.completion.SageApiIndexService
import com.starnotesxj.sageide.completion.SageApiIntelligenceFacade
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer
import com.starnotesxj.sageide.sugar.SageSugarInfo
import com.starnotesxj.sageide.type.SageTypeLowering
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeState

/**
 * Types the targets of Sage preparse-sugar statements.
 *
 * `F.<a> = GF(2^8, ...)` is built by [com.jetbrains.python.parsing.SageParser]
 * as a real multi-target assignment, and this provider gives:
 *
 * - the factory target `F` the return type of the constructor call `GF(...)`,
 *   resolved through the installed sage stubs (so `F.` completion works);
 * - each generator target (`a`) the element type of `F._first_ngens(...)`.
 *
 * The right-hand side references the generator targets (e.g. `modulus=x^8 + ...`
 * uses `x`), so `context.getType(call)` can re-enter this provider; the recursion
 * guard and the per-statement cache break the cycle.
 *
 * It also types two further cases by GENERAL preparse-semantics rules — never
 * by name whitelists (project rule: type knowledge lives in the stub data
 * layer; the plugin only mirrors the .sage language semantics the stubs
 * cannot express):
 *
 * - `_Type_*` factory attributes of the generated sage/all.pyi whose alias
 *   dangles (runtime-only `_with_category` subclass names) — followed to the
 *   real class via the name indexes;
 * - targets assigned a bare numeric literal: the Sage preparser wraps every
 *   integer literal as `Integer(...)` and float as `RealNumber(...)`
 *   (verified: `preparse("x = 5")` -> `x = Integer(5)`), so
 *   `ct = 2432...` is an Integer at runtime — this provider gives the target
 *   the converted instance type, which is what lets `ct.nth_root(3)`
 *   complete.  (Literals in other positions keep Python types: a PSI
 *   identifier's text must come from the document buffer, so the preparse
 *   wrapping cannot be reproduced in the parse tree without rewriting the
 *   file.)
 *
 * NOTE (v1.3.0): the return-type patches for unannotated sage stub methods
 * (`from_integer` and friends) were REMOVED — the stubgen curated table now
 * annotates them directly (`FiniteField_givaroElement | ...`), so the type
 * knowledge lives in the stubs, not in the IDE.  Registered `order="first"`
 * because the type-provider EP loops stop at the first non-null Ref (even a
 * null-content one), and this provider answers only for sugar targets in
 * `.sage` files.
 */
class SageTypeProvider : PyTypeProviderBase() {

    override fun getParameterType(
        param: PyNamedParameter,
        function: PyFunction,
        context: TypeEvalContext,
    ): Ref<PyType>? {
        val inferred = inferredParameterType(param, function, context)
        return inferred?.let { Ref.create(it) }
    }

    override fun getReferenceExpressionType(
        referenceExpression: com.jetbrains.python.psi.PyReferenceExpression,
        context: TypeEvalContext,
    ): PyType? {
        val file = referenceExpression.containingFile ?: return null
        if (!SageFileUtils.isSageFile(file)) return null
        if (referenceExpression.isQualified) return null

        // Unannotated parameters in a .sage function are ordinary reference
        // expressions when the editor asks for the type of a receiver.  Do not
        // leave this path to Python's structural/protocol inference: the same
        // conservative indexed-member proof used by getParameterType() can
        // materialize the active native .pyi class here as well.  This is also
        // the non-circular fallback used by directMemberAssignedType().
        val resolved = referenceExpression.reference.resolve()
        val parameter = (resolved as? PyNamedParameter)
            ?: if (resolved == null) {
                PsiTreeUtil.getParentOfType(referenceExpression, PyFunction::class.java)
                    ?.parameterList
                    ?.findParameterByName(referenceExpression.referencedName ?: return null)
            } else null
        if (parameter != null) {
            val function = PsiTreeUtil.getParentOfType(referenceExpression, PyFunction::class.java)
                ?: PsiTreeUtil.getParentOfType(parameter, PyFunction::class.java)
            val inferred = function?.let { inferredParameterType(parameter, it, context) }
            if (inferred != null) return inferred
            // A parameter reference is not an implicit sage.all name. Returning
            // null here preserves the native provider's result (including its
            // structural fallback) without allowing the namespace path below
            // to reinterpret a user parameter as a Sage global.
            return null
        }

        val name = referenceExpression.referencedName?.takeIf(String::isNotBlank) ?: return null
        val query = SageApiIndexService.getInstance().query() ?: return null
        val entry = query.namespaceEntry("sage.all", name) ?: return null
        // Native PSI/stub declarations and explicit imports remain authoritative.
        // The index fallback is only for an unresolved implicit sage.all root.
        if (referenceExpression.reference.resolve() != null) return null
        val facade = SageApiIntelligenceFacade.getInstance()
        val signatures = facade.signatures(entry.qualifiedName)
        if (signatures.isNotEmpty()) {
            return SageTypeLowering.lowerSignatures(signatures, referenceExpression, context, query)
        }
        val valueType = entry.valueType ?: return null
        return SageTypeLowering.lower(valueType, referenceExpression, context, query)
    }

    /**
     * Solves one unannotated parameter from direct member-call witnesses. The
     * index supplies candidate owners; active Sage stubs prove the selected
     * canonical class identity. No method or class name is special-cased.
     */
    private fun inferredParameterType(
        param: PyNamedParameter,
        function: PyFunction,
        context: TypeEvalContext,
    ): PyType? {
        val file = function.containingFile
        if (!SageFileUtils.isSageFile(file) || SageStubIndex.isSageStubFile(file)) return null
        if (param.annotationValue != null || param.typeCommentAnnotation != null) return null
        if (param.isPositionalContainer || param.isKeywordContainer) return null
        val parameterName = param.name?.takeIf { it.isNotBlank() } ?: return null
        val body = function.statementList
        if (PsiTreeUtil.collectElementsOfType(body, PyLambdaExpression::class.java).isNotEmpty()) return null

        val witnesses = PsiTreeUtil.collectElementsOfType(function.statementList, PyCallExpression::class.java)
            .asSequence()
            .filter { call ->
                PsiTreeUtil.getParentOfType(call, PyFunction::class.java, PyLambdaExpression::class.java) === function
            }
            .mapNotNull { call ->
                val callee = call.callee as? PyReferenceExpression ?: return@mapNotNull null
                val receiver = callee.qualifier as? PyReferenceExpression ?: return@mapNotNull null
                if (receiver.qualifier != null || receiver.referencedName != parameterName) return@mapNotNull null
                val resolvedReceiver = receiver.reference.resolve()
                if (resolvedReceiver != null &&
                    (resolvedReceiver !is PyNamedParameter || resolvedReceiver.name != parameterName)
                ) return@mapNotNull null
                if (resolvedReceiver == null && function.parameterList.findParameterByName(parameterName) !== param) {
                    return@mapNotNull null
                }
                if (callee.referencedName.isNullOrBlank()) return@mapNotNull null
                call to callee.referencedName!!
            }
            .toList()
        if (witnesses.isEmpty()) return null
        // A witness is valid only when its receiver is the declared parameter.
        // Keep this independent from the native resolver, whose fallback type
        // may be structural and therefore cannot prove the Sage owner.
        // The PSI can resolve a member call to an unrelated Python declaration while
        // the same syntax is a valid Sage witness. Candidate selection below is
        // intentionally independent of that native name resolution.
        // Each witness is checked against indexed signatures before any PSI type is published.
        if (hasUnsafeParameterBinding(param, function, witnesses.map { it.first })) return null
        // Only direct member calls are witnesses; assignment propagation is handled separately.

        val query = SageApiIndexService.getInstance().query() ?: return null
        val ownerCandidates = witnesses.map { (call, memberName) ->
            val viableOwners = query.index.entries
                .asSequence()
                .filter { it.kind == SageApiSymbolKind.CLASS }
                .map { it.qualifiedName }
                .distinct()
                .filter { owner ->
                    val classEntry = query.findAll(owner, SageApiSymbolKind.CLASS).singleOrNull() ?: return@filter false
                    val methods = query.members(classEntry.qualifiedName, memberName)
                    methods.any { entry ->
                        entry.kind == SageApiSymbolKind.METHOD &&
                            entry.signatures.any { signature -> hasSafeReturnContract(signature, call, context, query) }
                    } && classEntry.qualifiedName == owner && ownerIsActiveSageClass(param.project, owner)
                }
                .toSet()
            viableOwners
        }.reduce { left, right -> left intersect right }

        // Indexed member lookup intentionally includes inherited declarations, so
        // both a base and a subclass can explain the same witness set.  Prefer
        // owners that directly declare at least one observed member; this is a
        // data-driven specificity tie-break, not a Sage class/method allowlist.
        val directOwners = ownerCandidates.filter { owner ->
            witnesses.any { (_, memberName) ->
                query.entriesOwnedBy(owner).any { entry ->
                    entry.kind == SageApiSymbolKind.METHOD &&
                        entry.qualifiedName.substringAfterLast('.') == memberName
                }
            }
        }.toSet()
        val narrowedOwners = if (directOwners.isNotEmpty()) {
            ownerCandidates.intersect(directOwners)
        } else {
            ownerCandidates
        }
        // Different inheritance depths do not prove which concrete class a
        // parameter has.  Publishing the shallowest candidate here would make
        // a structurally compatible, but unrelated, Sage class look exact.
        // Only a single canonical owner is sufficient evidence.
        val owner = narrowedOwners.singleOrNull() ?: return null
        val classEntry = query.findAll(owner, SageApiSymbolKind.CLASS).singleOrNull() ?: return null
        if (classEntry.qualifiedName.isBlank() || classEntry.qualifiedName != owner) return null
        val activeClass = SageStubIndex.findClassByCanonicalName(param.project, owner)
            ?: SageStubIndex.findClass(param.project, owner.substringAfterLast('.'))?.takeIf {
                SageStubIndex.canonicalQualifiedName(it) == owner
            }
            ?: return null
        // Keep the exact indexed class selected by the witness intersection;
        // inherited member declarations are intentionally resolved by query.members.
        if (!activeClass.isValid || !SageStubIndex.isSageStubFile(activeClass.containingFile)) return null
        if (SageStubIndex.canonicalQualifiedName(activeClass) != classEntry.qualifiedName) return null
        return PyClassTypeImpl(activeClass, false)
    }

    // A class is materialized only after its canonical name and Sage-stub provenance agree.
    private fun ownerIsActiveSageClass(
        project: com.intellij.openapi.project.Project,
        owner: String,
    ): Boolean {
        val activeClass = SageStubIndex.findClassByCanonicalName(project, owner)
            ?: SageStubIndex.findClass(project, owner.substringAfterLast('.'))?.takeIf {
                SageStubIndex.canonicalQualifiedName(it) == owner
            }
            ?: return false
        return activeClass.isValid &&
            SageStubIndex.isSageStubFile(activeClass.containingFile) &&
            SageStubIndex.canonicalQualifiedName(activeClass) == owner
    }

    private fun hasSafeReturnContract(
        signature: SageApiSignature,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): Boolean = concreteSageReturnType(signature, anchor, context, query) != null

    /**
     * Assignment and parameter inference may only publish a type that the active
     * Sage stubs can prove. General lower() remains broad for ordinary callable
     * typing, but this boundary rejects structures that would otherwise hand the
     * native provider a misleading protocol/Any result.
     */
    private fun concreteSageReturnType(
        signature: SageApiSignature,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyClassType? {
        // A signature's declared KNOWN return is authoritative. Trusted evidence
        // may only fill an otherwise UNKNOWN declaration, and still has to pass
        // the same canonical active-stub checks below.
        val returnType = signature.returnType.takeIf { it.state == SageTypeState.KNOWN && !it.expression.isNullOrBlank() }
            ?: query.uniqueTrustedKnownReturnExpression(signature)
            ?: return null
        val expression = query.parseTypeExpression(returnType) as? com.starnotesxj.sagemath.sageapi.SageTypeExpression.Name
            ?: return null
        // The external index can legitimately omit a class entry while still
        // recording a fully-qualified return annotation for one of its methods.
        // The active .pyi tree is the authority for materialization, so an exact
        // Sage canonical name may be used directly once that tree proves it.
        // Keep the index lookup first for aliases and short, unambiguous names;
        // never infer a canonical owner from an unresolved or non-Sage name.
        val canonicalCandidates = buildList {
            query.resolveKnownClassName(expression.qualifiedName)?.let(::add)
            expression.qualifiedName.takeIf { it.startsWith("sage.") }?.let(::add)
        }.distinct()
        for (canonical in canonicalCandidates) {
            val activeClass = SageStubIndex.findClassByCanonicalName(anchor.project, canonical)
                ?: SageStubIndex.findClass(anchor.project, canonical.substringAfterLast('.'))?.takeIf {
                    SageStubIndex.canonicalQualifiedName(it) == canonical
                }
                ?: continue
            if (!activeClass.isValid || !SageStubIndex.isSageStubFile(activeClass.containingFile)) continue
            if (SageStubIndex.canonicalQualifiedName(activeClass) != canonical) continue
            return PyClassTypeImpl(activeClass, false)
        }
        return null
    }

    private fun hasUnsafeParameterBinding(
        param: PyNamedParameter,
        function: PyFunction,
        witnesses: List<PyCallExpression>,
    ): Boolean {
        val name = param.name ?: return true
        val firstWitness = witnesses.minOf { it.textRange.startOffset }
        return PsiTreeUtil.collectElementsOfType(function.statementList, PyTargetExpression::class.java)
            .asSequence()
            .filter { target ->
                PsiTreeUtil.getParentOfType(target, PyFunction::class.java, PyLambdaExpression::class.java) === function
            }
            .any { target ->
                target.name == name && target.qualifier == null && target.textRange.startOffset < firstWitness
            }
    }

    override fun getCallType(
        function: PyFunction,
        callSite: PyCallSiteExpression,
        context: TypeEvalContext,
    ): Ref<PyType>? {
        val qualifiedName = sageQualifiedName(function) ?: return null
        val query = SageApiIndexService.getInstance().query() ?: return null
        receiverSpecificMemberReturn(callSite, context, query, function)?.let { return Ref.create(it) }
        val signatures = query.signatures(qualifiedName)
        val lowered = SageTypeLowering.lowerCallReturnType(signatures, callSite, context, query, qualifiedName, function)
            ?: signatures.singleOrNull()
                ?.takeIf { it.parameters.isEmpty() }
                ?.let { SageTypeLowering.lower(it.returnType, callSite, context, query) }
            ?: return null
        return Ref.create(lowered)
    }

    private fun receiverSpecificMemberReturn(
        callSite: PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        function: PyFunction,
    ): PyType? {
        val call = callSite as? PyCallExpression ?: return null
        val callee = call.callee as? PyReferenceExpression ?: return null
        val receiver = callee.qualifier ?: callee.takeIf { !it.isQualified } ?: return null
        val receiverType = context.getType(receiver) as? PyClassType
            ?: (receiver.reference?.resolve() as? PyTargetExpression)?.let(context::getType) as? PyClassType
            ?: return null
        val owner = receiverType.pyClass.let(SageStubIndex::canonicalQualifiedName) ?: return null
        val memberName = callee.qualifier?.let { callee.referencedName } ?: "__call__"
        val indexedMembers = query.members(owner, memberName)
            .filter { it.kind == SageApiSymbolKind.METHOD && it.signatures.isNotEmpty() }
        if (indexedMembers.isEmpty()) return null
        // Prefer a declaration owned by the concrete receiver.  If it has no
        // override, inherited members remain available through query.members.
        val owned = indexedMembers.filter { it.qualifiedName.substringBeforeLast('.') == owner }
        val candidates = if (owned.isNotEmpty()) owned else indexedMembers
        if (candidates.size != 1) return null
        val member = candidates.single()
        return SageTypeLowering.lowerCallReturnType(
            member.signatures,
            call,
            context,
            query,
            member.qualifiedName,
            function,
        )
    }

    private fun sageQualifiedName(function: PyFunction): String? {
        function.qualifiedName?.takeIf { it.startsWith("sage.") }?.let { return it }
        val moduleName = function.containingFile.virtualFile?.path
            ?.replace('\\', '/')
            ?.substringAfter("/site-packages/")
            ?.removeSuffix(".pyi")
            ?.replace('/', '.')
            ?.removeSuffix(".__init__")
        val name = function.name
        return if (moduleName?.startsWith("sage.") == true && !name.isNullOrBlank()) "$moduleName.$name" else null
    }

    override fun getReferenceType(
        referenceTarget: PsiElement,
        context: TypeEvalContext,
        anchor: PsiElement?,
    ): Ref<PyType>? {
        val target = referenceTarget as? PyTargetExpression ?: return null
        // Factory attributes in the generated sage/all.pyi whose `_Type_*`
        // annotation alias dangles: `CC: _Type_CC` imports
        // `ComplexField_class_with_category`, a RUNTIME-ONLY subclass name —
        // the stubs only declare `ComplexField_class`, so the annotation
        // fails to resolve and `CC` loses both its type (`CC()` untyped) and
        // its __call__-based callability (no parens in completion).  Follow
        // the alias (with the `_with_category` fallback) to the real class
        // and return its INSTANCE type.  Only answers inside the sage stub
        // tree; everywhere else the sugar handling below applies or null is
        // returned.
        if (SageStubIndex.isSageStubFile(target.containingFile)) {
            val type = sageAllFactoryAttributeType(target) ?: return null
            return Ref.create(type)
        }
        val isSageFile = SageFileUtils.isSageFile(target.containingFile)
        val statement = PsiTreeUtil.getParentOfType(target, PyAssignmentStatement::class.java)

        if (isSageFile && statement != null && !SageSugarAnalyzer.shapePredicate(statement)) {
            val rhsCall = target.findAssignedValue() as? PyCallExpression
            if (rhsCall != null) {
                directMemberAssignedType(target, rhsCall, context)?.let { return it }
            }
            genericFactoryAssignedType(target, context)?.let { return it }
            return literalAssignedType(target)
        }

        if (isSageFile && statement != null) {
            val sugarResult = if (SageSugarAnalyzer.shapePredicate(statement)) {
                RecursionManager.doPreventingRecursion(target, true) {
                    val info = SageSugarAnalyzer.analyze(statement) ?: return@doPreventingRecursion null
                    val factoryType = factoryType(statement, info, context)
                    if (factoryType == null) return@doPreventingRecursion null

                    val type: PyType? = when {
                        target === info.factoryTarget -> factoryType
                        target in info.nameTargets -> generatorType(factoryType, context)
                        else -> null
                    }
                    type?.let { Ref.create(it) }
                }
            } else null
            if (sugarResult != null) return sugarResult
        }

        val indexedFactory = genericFactoryAssignedType(target, context)
        if (indexedFactory != null) return indexedFactory

        // The Sage preparser wraps EVERY numeric literal (verified against
        // sage.repl.preparse: `x = 5` -> `x = Integer(5)`, `x = 1.5` ->
        // `x = RealNumber('1.5')`), so `ct = 2432...` is a Sage Integer at
        // runtime while the raw PSI literal types as Python int — which is
        // why `ct.nth_root(3)` had no member completion.  Mirror the
        // preparse conversion at the ASSIGNMENT boundary: a .sage target
        // assigned a bare int/float literal gets the converted class type.
        if (isSageFile) return literalAssignedType(target)
        return null
    }

    /** Resolve an explicitly resolved Sage call from the versioned API return type. */
    private fun directMemberAssignedType(
        target: PyTargetExpression,
        call: PyCallExpression,
        context: TypeEvalContext,
    ): Ref<PyType>? {
        val assignment = PsiTreeUtil.getParentOfType(target, PyAssignmentStatement::class.java) ?: return null
        if (assignment.targets.size != 1 || assignment.targets.singleOrNull() !== target) return null
        if (!SageFileUtils.isSageFile(target.containingFile)) return null
        val function = PsiTreeUtil.getParentOfType(target, PyFunction::class.java) ?: return null
        if (PsiTreeUtil.getParentOfType(assignment, PyFunction::class.java) !== function) return null
        // The Python PSI may wrap a function body in a suite node; direct
        // member propagation is still safe because the assignment and receiver
        // checks below constrain the same function and parameter.
        val assignedValue = target.findAssignedValue() as? PyCallExpression ?: return null
        if (assignedValue !== call && assignedValue.text != call.text) return null
        val callee = call.callee as? PyReferenceExpression ?: return null
        val receiver = callee.qualifier as? PyReferenceExpression ?: return null
        if (receiver.qualifier != null) return null
        val resolvedReceiver = receiver.reference.resolve()
        val parameter = when {
            resolvedReceiver is PyNamedParameter -> resolvedReceiver
            resolvedReceiver == null -> function.parameterList
                .findParameterByName(receiver.referencedName ?: return null)
                ?: return null
            else -> return null
        }
        if (parameter.annotationValue != null || parameter.typeCommentAnnotation != null) return null
        if (hasUnsafeParameterBinding(parameter, function, listOf(call))) return null
        val query = SageApiIndexService.getInstance().query() ?: return null
        // Resolve the parameter from the same indexed witness proof first.
        // context.getType(receiver) may already be Python's structural
        // {member,...} result, and using it here makes assignment propagation
        // depend on the very type we are trying to replace.
        val receiverType = inferredParameterType(parameter, function, context) as? PyClassType
            ?: return null
        val receiverClass = receiverType.pyClass.takeIf { it.isValid } ?: return null
        if (!SageStubIndex.isSageStubFile(receiverClass.containingFile)) return null
        val receiverOwner = SageStubIndex.canonicalQualifiedName(receiverClass) ?: return null
        val members = query.members(receiverOwner, callee.referencedName.orEmpty())
            .filter { it.kind == SageApiSymbolKind.METHOD && it.signatures.isNotEmpty() }
        if (members.size != 1) return null
        val member = members.single()
        val viable = SageTypeLowering.viableSignatures(
            member.signatures,
            call,
            context,
            query,
            member.qualifiedName,
            null,
        )
        if (viable.size != 1) return null
        val signature = viable.single()
        if (concreteSageReturnType(signature, assignedValue, context, query) == null) return null
        val lowered = concreteSageReturnType(signature, assignedValue, context, query)
            ?: return null
        return Ref.create(lowered)
    }

    private fun genericFactoryAssignedType(target: PyTargetExpression, context: TypeEvalContext): Ref<PyType>? {
        RecursionManager.doPreventingRecursion(target, true) {
            val call = target.findAssignedValue() as? PyCallExpression ?: return@doPreventingRecursion null
            directMemberAssignedType(target, call, context)
        }?.let { return it }
        val call = target.findAssignedValue() as? PyCallExpression ?: return null
        val sageFile = SageFileUtils.isSageFile(target.containingFile)
        val query = SageApiIndexService.getInstance().query() ?: return null
        val resolvedNames = call.multiResolveCalleeFunction(
            com.jetbrains.python.psi.resolve.PyResolveContext.defaultContext(context),
        )
            .mapNotNull { function ->
                function.qualifiedName?.takeIf { it.startsWith("sage.") }
                    ?: (function as? PyFunction)?.let { resolved ->
                        val file = runCatching { resolved.containingFile }.getOrNull()
                        val moduleName = file?.virtualFile?.path?.replace('\\', '/')
                            ?.substringAfter("/site-packages/")
                            ?.removeSuffix(".pyi")
                            ?.replace('/', '.')
                            ?.removeSuffix(".__init__")
                        val name = resolved.name
                        if (moduleName?.startsWith("sage.") == true && !name.isNullOrBlank()) "$moduleName.$name" else null
                    }
            }
            .distinct()
        val implicitQualifiedNames = if (sageFile && resolvedNames.isEmpty()) {
            val rootReference = call.callee as? com.jetbrains.python.psi.PyReferenceExpression
            if (rootReference != null && !rootReference.isQualified && rootReference.reference.resolve() == null) {
                rootReference.referencedName?.let { name ->
                    query.namespaceEntry("sage.all", name)?.let { listOf(it.qualifiedName) }.orEmpty()
                }.orEmpty()
            } else emptyList()
        } else emptyList()
        // Native PSI resolves E(...) and E.method(...) through the declaration
        // it first sees in a base class.  That declaration is valid for member
        // lookup, but is not a final return-type contract when E already has a
        // concrete canonical Sage class.  Prefer the concrete receiver's own
        // indexed member contract for every instance call; only then fall back
        // to the native/base declaration or an implicit sage.all factory.
        val receiverSpecificNames = receiverSpecificMemberNames(call, context, query)
        val qualifiedNames = (if (receiverSpecificNames.isNotEmpty()) {
            receiverSpecificNames
        } else {
            resolvedNames + implicitQualifiedNames
        }).distinct()
        val qualifiedName = qualifiedNames.singleOrNull() ?: return null
        val signatures = query.signatures(qualifiedName)
        val lowered = SageTypeLowering.lowerCallReturnType(
            signatures,
            call,
            context,
            query,
            qualifiedName,
            null,
        ) ?: signatures.singleOrNull()
            ?.let { concreteSageReturnType(it, target, context, query) }
            ?: return null
        return Ref.create(lowered)
    }

    private fun receiverSpecificMemberNames(
        call: PyCallExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): List<String> {
        val callee = call.callee as? PyReferenceExpression ?: return emptyList()
        val receiver = callee.qualifier ?: callee.takeIf { !it.isQualified } ?: return emptyList()
        val receiverType = context.getType(receiver) as? PyClassType
            ?: (receiver.reference?.resolve() as? PyTargetExpression)?.let(context::getType) as? PyClassType
            ?: return emptyList()
        val owner = SageStubIndex.canonicalQualifiedName(receiverType.pyClass) ?: return emptyList()
        val memberName = callee.qualifier?.let { callee.referencedName } ?: "__call__"
        val members = query.members(owner, memberName)
            .filter { it.kind == SageApiSymbolKind.METHOD && it.signatures.isNotEmpty() }
        if (members.isEmpty()) return emptyList()
        val owned = members.filter { it.qualifiedName.substringBeforeLast('.') == owner }
        return (if (owned.isNotEmpty()) owned else members).map { it.qualifiedName }
    }

    /** `x = <int literal>` -> Integer, `x = <float literal>` -> RealNumber. */
    private fun literalAssignedType(target: PyTargetExpression): Ref<PyType>? {
        val assigned = target.findAssignedValue() as? PyNumericLiteralExpression ?: return null
        val className = when {
            assigned.isIntegerLiteral -> "sage.rings.integer.Integer"
            assigned.node?.elementType == PyElementTypes.FLOAT_LITERAL_EXPRESSION -> "sage.rings.real_mpfr.RealNumber"
            else -> return null
        }
        val cls = SageStubIndex.findClassByCanonicalName(target.project, className) ?: return null
        if (!cls.isValid) return null
        return Ref.create(PyClassTypeImpl(cls, false))
    }

    private fun factoryType(
        statement: PyAssignmentStatement,
        info: SageSugarInfo,
        context: TypeEvalContext,
    ): PyType? {
        statement.getUserData(FACTORY_TYPE_KEY)?.let { return it }
        val call = info.call ?: return null
        val type = context.getType(call) ?: return null
        statement.putUserData(FACTORY_TYPE_KEY, type)
        return type
    }

    /** `(a,) = F._first_ngens(1)` — the generator type is the element type of the tuple. */
    private fun generatorType(factoryType: PyType, context: TypeEvalContext): PyType? {
        val pyClass = (factoryType as? PyClassType)?.pyClass?.takeIf { it.isValid } ?: return null
        val firstNgens = pyClass.findMethodByName("_first_ngens", true, context) ?: return null
        val callable = context.getType(firstNgens) as? PyCallableType ?: return null
        val returnType = callable.getReturnType(context) ?: return null
        return (returnType as? PyTupleType)?.getElementType(0) ?: returnType
    }

    /**
     * The instance type of a `Name: _Type_Name` factory attribute in the
     * generated `sage/all.pyi`, resolved by following the `_Type_Name`
     * from-import alias to the real class (with the `_with_category`
     * fallback).  Null for anything that is not such an attribute or whose
     * alias cannot be followed.
     */
    private fun sageAllFactoryAttributeType(target: PyTargetExpression): PyType? {
        val file = try {
            target.containingFile
        } catch (_: RuntimeException) {
            null
        } as? com.jetbrains.python.psi.PyFile
        if (file == null) return null
        // `getAnnotationValue()` returns the annotation TEXT String on this
        // platform (the stub's annotation string), NOT a PyExpression.
        val aliasName = target.annotationValue
        if (aliasName == null || !aliasName.startsWith("_Type_")) return null
        for (fromImport in file.fromImports) {
            for (importElement in fromImport.importElements) {
                if (importElement.visibleName != aliasName) continue
                val moduleQName = fromImport.importSource?.asQualifiedName()?.toString()
                val importedName = importElement.importedQName?.lastComponent ?: aliasName
                val cls = SageStubIndex.findAliasClass(target.project, moduleQName, importedName)
                if (cls == null) continue
                if (!cls.isValid) continue
                return PyClassTypeImpl(cls, false)
            }
        }
        return null
    }

    companion object {
        private val FACTORY_TYPE_KEY = Key.create<PyType>("sageide.sugar.factoryType")
    }
}
