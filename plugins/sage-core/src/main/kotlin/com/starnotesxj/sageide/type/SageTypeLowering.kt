package com.starnotesxj.sageide.type

import com.intellij.psi.PsiElement
import com.intellij.openapi.util.RecursionManager
import com.jetbrains.python.ast.PyAstFunction
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyKeywordArgument
import com.jetbrains.python.psi.PyExpression
import com.jetbrains.python.psi.PyQualifiedExpression
import com.jetbrains.python.psi.PyStarArgument
import com.jetbrains.python.psi.PyStringElement
import com.jetbrains.python.psi.impl.PyBuiltinCache
import com.jetbrains.python.psi.types.PyAnyType
import com.jetbrains.python.psi.types.PyLiteralType
import com.jetbrains.python.psi.types.PyTypeChecker
import com.jetbrains.python.psi.types.PyCallableParameter
import com.jetbrains.python.psi.types.PyCallableParameterImpl
import com.jetbrains.python.psi.types.PyCallableType
import com.jetbrains.python.psi.types.PyCallableTypeImpl
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyClassTypeImpl
import com.jetbrains.python.psi.types.PyCollectionTypeImpl
import com.jetbrains.python.psi.types.PyOverloadType
import com.jetbrains.python.psi.types.PyTupleType
import com.jetbrains.python.psi.types.PyType
import com.jetbrains.python.psi.types.PyUnionType
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageTypeExpression
import com.starnotesxj.sagemath.sageapi.SageTypeRef
import com.starnotesxj.sagemath.sageapi.SageTypeRefExpressionParser
import com.starnotesxj.sageide.sugar.SageStubIndex

/**
 * Lowers index type expressions to the platform's real PyType graph.
 *
 * Index metadata is additive and may describe symbols absent from the active
 * interpreter stubs. Such symbols remain untyped here rather than becoming a
 * fabricated PSI class; completion/documentation can still use the index.
 */
object SageTypeLowering {
    fun lower(
        type: SageTypeRef,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyType? = SageTypeRefExpressionParser.parse(type)?.let { lower(it, anchor, context, query) }

    fun lower(
        expression: SageTypeExpression,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        bindings: Map<String, PyType> = emptyMap(),
    ): PyType? = when (expression) {
        is SageTypeExpression.Name -> lowerName(expression.qualifiedName, anchor, query)
        is SageTypeExpression.TypeVariable -> bindings[expression.name]
        is SageTypeExpression.ParamSpecAccess -> null
        SageTypeExpression.NoneType -> PyBuiltinCache.getInstance(anchor).noneType
        SageTypeExpression.EllipsisType -> null
        is SageTypeExpression.Optional -> {
            val element = lower(expression.element, anchor, context, query, bindings) ?: return null
            val noneType = PyBuiltinCache.getInstance(anchor).noneType ?: return null
            PyUnionType.union(listOf(element, noneType))
        }
        is SageTypeExpression.Union -> lowerUnionAtomically(expression.members.map { lower(it, anchor, context, query, bindings) })
        is SageTypeExpression.Generic -> lowerGeneric(expression, anchor, context, query, bindings)
        is SageTypeExpression.Literal -> lowerLiteral(expression, anchor, query)
        is SageTypeExpression.Callable -> lowerCallable(expression, anchor, context, query, bindings)
    }

    fun lowerSignature(
        signature: SageApiSignature,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyCallableType? {
        val returnType = lower(signature.returnType, anchor, context, query) ?: return null
        val parameters = mutableListOf<PyCallableParameter>()
        var hasPositionalOnly = false
        var positionalOnlySeparatorAdded = false
        var keywordOnlySeparatorAdded = false
        signature.parameters.forEach { parameter ->
            if (parameter.positionalOnly) hasPositionalOnly = true
            if (hasPositionalOnly && !parameter.positionalOnly && !positionalOnlySeparatorAdded) {
                parameters += PyCallableParameterImpl.positionalOnlySeparatorNonPsi()
                positionalOnlySeparatorAdded = true
            }
            if (parameter.keywordOnly && !keywordOnlySeparatorAdded && parameters.none { it.isKeywordOnlySeparator }) {
                parameters += PyCallableParameterImpl.keywordOnlySeparatorNonPsi()
                keywordOnlySeparatorAdded = true
            }
            parameters += lowerParameter(parameter, anchor, context, query) ?: return null
        }
        if (hasPositionalOnly && !positionalOnlySeparatorAdded) {
            parameters += PyCallableParameterImpl.positionalOnlySeparatorNonPsi()
        }
        return PyCallableTypeImpl(parameters, returnType)
    }

    fun lowerSignatures(
        signatures: List<SageApiSignature>,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyType? {
        val callables = signatures.mapNotNull { lowerSignature(it, anchor, context, query) }
        if (callables.size != signatures.size || callables.isEmpty()) return null
        return if (callables.size == 1) callables.single() else PyOverloadType(callables, null)
    }

    /**
     * Lower only overloads whose indexed parameter contract accepts this call.
     * The platform still owns expression typing; an unknown argument therefore
     * remains compatible with a known parameter, while it never creates a
     * deterministic choice between multiple viable signatures.
     */
    fun viableSignatures(
        signatures: List<SageApiSignature>,
        callSite: com.jetbrains.python.psi.PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        callableQualifiedName: String? = null,
        callable: com.jetbrains.python.psi.PyFunction? = null,
    ): List<SageApiSignature> {
        val arguments = callSite.getArguments(null)
        return signatures.mapNotNull { signature ->
            signatureBindings(signature, arguments, callSite, context, query, callableQualifiedName, callable)?.let { signature }
        }
    }

    fun lowerCallReturnType(
        signatures: List<SageApiSignature>,
        callSite: com.jetbrains.python.psi.PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        callableQualifiedName: String? = null,
        callable: com.jetbrains.python.psi.PyFunction? = null,
    ): PyType? {
        val arguments = callSite.getArguments(null)
        val viable = signatures.mapNotNull { signature ->
            signatureBindings(signature, arguments, callSite, context, query, callableQualifiedName, callable)?.let { signature to it }
        }
        if (viable.size != 1) return null
        val (signature, bindings) = viable.single()
        val names = signature.typeParameters.map { it.name }.toSet()
        val paramSpecNames = signature.typeParameters
            .filter { it.kind == com.starnotesxj.sagemath.sageapi.SageApiTypeParameterKind.PARAM_SPEC }
            .map { it.name }
            .toSet()
        val expression = signature.returnType.expression?.let {
            SageTypeRefExpressionParser.parse(it, names, paramSpecNames)
        } ?: return null
        return lower(expression, callSite, context, query, bindings)
    }

    private fun literalFallbackType(argument: PyExpression?): PyType? {
        return when (argument) {
            is com.jetbrains.python.psi.PyNumericLiteralExpression -> {
                val cache = PyBuiltinCache.getInstance(argument)
                if (argument.isIntegerLiteral) cache.intType else cache.floatType
            }
            is com.jetbrains.python.psi.PyStringLiteralExpression -> PyBuiltinCache.getInstance(argument).strType
            else -> null
        }
    }

    private fun bindExpression(
        expected: SageTypeExpression,
        argument: PyExpression?,
        bindings: MutableMap<String, PyType>,
        context: TypeEvalContext,
        anchor: PsiElement,
        query: SageApiIndexQuery,
        typeParameters: Map<String, com.starnotesxj.sagemath.sageapi.SageApiTypeParameter>,
    ): Boolean {
        val platformType = argument?.let { context.getType(it) }
            ?.takeUnless { it == PyAnyType.Any || it == PyAnyType.Unknown }
        val candidates = listOfNotNull(
            platformType,
            indexedNestedCallType(argument, context, anchor, query),
            literalFallbackType(argument),
        ).distinct()
        for (actual in candidates) {
            val originalBindings = bindings.toMap()
            if (bindTypeExpression(
                    expected,
                    actual,
                    bindings,
                    context,
                    anchor,
                    query,
                    typeParameters,
                )
            ) {
                return true
            }
            bindings.clear()
            bindings.putAll(originalBindings)
        }
        return false
    }

    /**
     * During an outer factory overload match, the platform can still be
     * calculating the type of a nested Sage factory call.  A single indexed
     * signature with no typed parameters is nevertheless an exact, non-guessy
     * contract (for example a factory whose input domain is intentionally
     * dynamic).  Materialize only that narrow case; calls with parameters or
     * overloads remain unknown until the platform can type their arguments.
     */
    private fun indexedNestedCallType(
        argument: PyExpression?,
        context: TypeEvalContext,
        anchor: PsiElement,
        query: SageApiIndexQuery,
    ): PyType? {
        val call = argument as? PyCallExpression ?: return null
        val callee = call.callee as? com.jetbrains.python.psi.PyReferenceExpression ?: return null
        val function = callee.reference.resolve() as? PyFunction
        val resolvedName = function?.let(::sageQualifiedName)
        val implicitName = if (resolvedName == null && !callee.isQualified) {
            callee.referencedName?.let { query.namespaceEntry("sage.all", it)?.qualifiedName }
        } else null
        val qualifiedName = resolvedName ?: implicitName ?: return null
        val signatures = query.signatures(qualifiedName)
        if (signatures.isEmpty()) return null
        // A nested Sage factory is safe to materialize whenever its own
        // contract selects exactly one overload.  This covers parameterized
        // factories such as GF(11), while retaining the same fail-closed rule
        // for ambiguous or dynamic calls.
        return RecursionManager.doPreventingRecursion(call, true) {
            lowerCallReturnType(signatures, call, context, query, qualifiedName, function)
        }
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
        if (moduleName?.startsWith("sage.") == true && !name.isNullOrBlank()) {
            function.containingClass?.name?.takeIf { it.isNotBlank() }?.let { owner ->
                return "$moduleName.$owner.$name"
            }
            return "$moduleName.$name"
        }
        return null
    }

    private fun bindTypeExpression(
        expected: SageTypeExpression,
        actual: PyType,
        bindings: MutableMap<String, PyType>,
        context: TypeEvalContext,
        anchor: PsiElement,
        query: SageApiIndexQuery,
        typeParameters: Map<String, com.starnotesxj.sagemath.sageapi.SageApiTypeParameter>,
    ): Boolean {
        when (expected) {
            is SageTypeExpression.TypeVariable -> {
                val declaration = typeParameters[expected.name] ?: return false
                if (declaration.kind == com.starnotesxj.sagemath.sageapi.SageApiTypeParameterKind.PARAM_SPEC) return false
                if (actual == PyAnyType.Any || actual == PyAnyType.Unknown) return false
                if (!typeParameterAccepts(declaration, actual, context, anchor, query)) return false
                val previous = bindings[expected.name]
                if (previous == null) {
                    bindings[expected.name] = actual
                    return true
                }
                return PyTypeChecker.match(previous, actual, context) && PyTypeChecker.match(actual, previous, context)
            }
            is SageTypeExpression.Optional -> {
                val direct = LinkedHashMap(bindings)
                if (bindTypeExpression(expected.element, actual, direct, context, anchor, query, typeParameters)) {
                    bindings.clear()
                    bindings.putAll(direct)
                    return true
                }
                return false
            }
            is SageTypeExpression.Union -> {
                val candidates = expected.members.mapNotNull { member ->
                    val candidate = LinkedHashMap(bindings)
                    if (bindTypeExpression(member, actual, candidate, context, anchor, query, typeParameters)) candidate else null
                }
                if (candidates.size != 1) return false
                bindings.clear()
                bindings.putAll(candidates.single())
                return true
            }
            is SageTypeExpression.ParamSpecAccess -> return false
            is SageTypeExpression.Generic -> {
                val actualClass = actual as? PyClassType ?: return false
                val expectedName = normalizeName(expected.base.qualifiedName)
                if (actualClass.classQName != expectedName && actualClass.name != expected.base.qualifiedName.substringAfterLast('.')) return false
                val actualArguments = actualClass.typeArguments
                if (actualArguments.size != expected.arguments.size) return false
                val candidate = LinkedHashMap(bindings)
                if (!expected.arguments.zip(actualArguments).all { (expectedArgument, actualArgument) ->
                        bindTypeExpression(expectedArgument, actualArgument, candidate, context, anchor, query, typeParameters)
                    }) return false
                bindings.clear()
                bindings.putAll(candidate)
                return true
            }
            else -> {
                val expectedType = lower(expected, anchor, context, query)
                return expectedType != null && PyTypeChecker.match(expectedType, actual, context)
            }
        }
    }

    private fun resolveSelfReceiver(
        callSite: com.jetbrains.python.psi.PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        callableQualifiedName: String?,
        callable: com.jetbrains.python.psi.PyFunction?,
    ): PyType? {
        if (callable?.let { it.modifier == PyAstFunction.Modifier.STATICMETHOD } == true) return null
        val callExpression = callSite as? PyCallExpression ?: return null
        val callee = callExpression.callee as? PyQualifiedExpression ?: return null
        val receiver = callee.qualifier ?: return null
        val receiverType = context.getType(receiver) as? PyClassType ?: return null
        if (receiverType.isDefinition) return null
        val instanceType = receiverType
        val canonicalReceiver = SageStubIndex.canonicalQualifiedName(instanceType.pyClass) ?: return null
        if (!canonicalReceiver.startsWith("sage.")) return null
        val owner = callableQualifiedName?.substringBeforeLast('.', missingDelimiterValue = "")?.takeIf { it.isNotBlank() }
            ?: return null
        val ownerNames = query.reachableTypeNames(canonicalReceiver)
        if (owner !in ownerNames) return null
        return instanceType
    }

    private fun typeParameterAccepts(
        declaration: com.starnotesxj.sagemath.sageapi.SageApiTypeParameter,
        actual: PyType,
        context: TypeEvalContext,
        anchor: PsiElement,
        query: SageApiIndexQuery,
    ): Boolean {
        val bound = declaration.bound
        if (bound != null) {
            val boundType = lower(bound, anchor, context, query) ?: return false
            if (!PyTypeChecker.match(boundType, actual, context)) return false
        }
        if (declaration.constraints.isNotEmpty()) {
            val matches = declaration.constraints.count { constraint ->
                val constraintType = lower(constraint, anchor, context, query)
                constraintType != null && PyTypeChecker.match(constraintType, actual, context)
            }
            if (matches != 1) return false
        }
        return true
    }

    private fun signatureBindings(
        signature: SageApiSignature,
        arguments: List<PyExpression>,
        callSite: com.jetbrains.python.psi.PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        callableQualifiedName: String?,
        callable: com.jetbrains.python.psi.PyFunction?,
    ): Map<String, PyType>? {
        val typeParameters = signature.typeParameters.associateBy { it.name }
        if (typeParameters.values.any { it.kind == com.starnotesxj.sagemath.sageapi.SageApiTypeParameterKind.PARAM_SPEC }) return null
        val bindings = linkedMapOf<String, PyType>()
        if (typeParameters.values.any { it.kind == com.starnotesxj.sagemath.sageapi.SageApiTypeParameterKind.SELF }) {
            val selfType = resolveSelfReceiver(callSite, context, query, callableQualifiedName, callable) ?: return null
            bindings["Self"] = selfType
        }
        val parameters = signature.parameters
        val positional = parameters.filter { !it.keywordOnly && !it.variadic }
        val positionalContainer = parameters.firstOrNull { it.variadic && !it.keywordOnly }
        val keywordContainer = parameters.firstOrNull { it.variadic && it.keywordOnly }
        val consumed = mutableSetOf<String>()
        var positionalIndex = 0
        fun bind(parameter: SageApiParameter, expression: PyExpression?): Boolean {
            val expectedExpression = parameter.type.expression
            val names = signature.typeParameters.map { it.name }.toSet()
            val paramSpecNames = signature.typeParameters
                .filter { it.kind == com.starnotesxj.sagemath.sageapi.SageApiTypeParameterKind.PARAM_SPEC }
                .map { it.name }
                .toSet()
            val parsed = expectedExpression?.let { SageTypeRefExpressionParser.parse(it, names, paramSpecNames) }
            if (parsed == null || parsed is SageTypeExpression.Name || parsed is SageTypeExpression.NoneType || parsed is SageTypeExpression.EllipsisType) {
                return argumentValueCompatible(expression, parameter.type, context, query)
            }
            val bound = bindExpression(parsed, expression, bindings, context, callSite, query, typeParameters)
            if (!bound) return false
            return true
        }
        for (argument in arguments) {
            if (argument is PyStarArgument) return null
            val keyword = (argument as? PyKeywordArgument)?.keyword
            if (keyword != null) {
                val parameter = parameters.firstOrNull { it.name == keyword }
                if (parameter == null) {
                    if (keywordContainer == null || !argumentValueCompatible(argument.valueExpression, keywordContainer.type, context, query)) return null
                } else {
                    if (parameter.positionalOnly || !consumed.add(parameter.name) || !bind(parameter, argument.valueExpression)) return null
                }
                continue
            }
            while (positionalIndex < positional.size && positional[positionalIndex].name in consumed) positionalIndex++
            val parameter = positional.getOrNull(positionalIndex++)
            if (parameter == null) {
                if (positionalContainer == null || !argumentValueCompatible(argument, positionalContainer.type, context, query)) return null
            } else {
                if (!consumed.add(parameter.name) || !bind(parameter, argument)) return null
            }
        }
        if (parameters.any { !it.optional && !it.variadic && it.name !in consumed }) return null
        if (!signatureAcceptsCall(signature, arguments, context, query)) return null
        return bindings
    }

    private fun signatureAcceptsCall(
        signature: SageApiSignature,
        arguments: List<com.jetbrains.python.psi.PyExpression>,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): Boolean {
        val parameters = signature.parameters
        val positional = parameters.filter { !it.keywordOnly && !it.variadic }
        val positionalContainer = parameters.firstOrNull { it.variadic && !it.keywordOnly }
        val keywordContainer = parameters.firstOrNull { it.variadic && it.keywordOnly }
        val consumed = mutableSetOf<String>()
        var positionalIndex = 0
        for (argument in arguments) {
            if (argument is com.jetbrains.python.psi.PyStarArgument) return false
            val keyword = (argument as? com.jetbrains.python.psi.PyKeywordArgument)?.keyword
            if (keyword != null) {
                val parameter = parameters.firstOrNull { it.name == keyword }
                if (parameter == null) {
                    if (keywordContainer == null) return false
                    if (!argumentValueCompatible(argument.valueExpression, keywordContainer.type, context, query)) return false
                } else {
                    if (parameter.positionalOnly || !consumed.add(parameter.name)) return false
                    if (!argumentValueCompatible(argument.valueExpression, parameter.type, context, query)) return false
                }
                continue
            }
            while (positionalIndex < positional.size && positional[positionalIndex].name in consumed) positionalIndex++
            val parameter = positional.getOrNull(positionalIndex++)
            if (parameter == null) {
                if (positionalContainer == null) return false
                if (!argumentValueCompatible(argument, positionalContainer.type, context, query)) return false
            } else {
                if (!consumed.add(parameter.name)) return false
                if (!argumentValueCompatible(argument, parameter.type, context, query)) return false
            }
        }
        return parameters.filter { !it.optional && !it.variadic }.all { it.name in consumed }
    }

    private fun argumentValueCompatible(
        expression: com.jetbrains.python.psi.PyExpression?,
        expected: SageTypeRef,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): Boolean {
        if (expression == null || expected.state != com.starnotesxj.sagemath.sageapi.SageTypeState.KNOWN) return true
        val literalName = when (expression) {
            is com.jetbrains.python.psi.PyNumericLiteralExpression ->
                if (expression.isIntegerLiteral) "int" else "float"
            is com.jetbrains.python.psi.PyStringLiteralExpression -> "str"
            else -> null
        }
        if (literalName != null) {
            // Lightweight fixture projects may not have a Python SDK, so the
            // platform cannot always materialize builtin int/str PyClassTypes.
            // Literal syntax still gives an exact answer for builtin overloads.
            val expectedName = expected.expression?.substringAfterLast('.')?.substringBefore('[')?.trim()
            if (expectedName in setOf("bool", "int", "float", "str", "bytes")) {
                return expectedName == literalName
            }
        }
        val expectedType = lower(expected, expression, context, query) ?: return true
        val platformType = context.getType(expression)
            ?.takeUnless { it == PyAnyType.Any || it == PyAnyType.Unknown }
        val literalType = (expression as? com.jetbrains.python.psi.PyNumericLiteralExpression)?.let {
                if (it.isIntegerLiteral) PyBuiltinCache.getInstance(expression).intType else PyBuiltinCache.getInstance(expression).floatType
            }
            ?: (expression as? com.jetbrains.python.psi.PyStringLiteralExpression)?.let {
                PyBuiltinCache.getInstance(expression).strType
            }
        val actualCandidates = listOfNotNull(
            platformType,
            indexedNestedCallType(expression, context, expression, query),
            literalType,
        ).distinct()
        if (actualCandidates.isEmpty()) return true
        return actualCandidates.any { actual ->
            val expectedCanonical = (expectedType as? PyClassType)?.pyClass
                ?.let(SageStubIndex::canonicalQualifiedName)
            val actualCanonical = (actual as? PyClassType)?.pyClass
                ?.let(SageStubIndex::canonicalQualifiedName)
            actual == expectedType ||
                (expectedCanonical != null && expectedCanonical == actualCanonical) ||
                actual is com.jetbrains.python.psi.types.PyAnyType ||
                expectedType is com.jetbrains.python.psi.types.PyAnyType ||
                PyTypeChecker.match(expectedType, actual, context)
        }
    }

    private fun lowerParameter(
        parameter: SageApiParameter,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyCallableParameter? {
        val type = lower(parameter.type, anchor, context, query) ?: return null
        if (parameter.variadic) {
            return if (parameter.keywordOnly) {
                PyCallableParameterImpl.keywordContainerNonPsi(parameter.name, type)
            } else {
                PyCallableParameterImpl.positionalContainerNonPsi(parameter.name, type)
            }
        }
        return PyCallableParameterImpl.nonPsi(parameter.name, type, parameter.defaultValue)
    }

    private fun lowerCallable(
        expression: SageTypeExpression.Callable,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        bindings: Map<String, PyType> = emptyMap(),
    ): PyType? {
        val returnType = lower(expression.returnType, anchor, context, query, bindings) ?: return null
        val parameterTypes = expression.parameters?.map { lower(it, anchor, context, query, bindings) ?: return null }
        val parameters = parameterTypes?.mapIndexed { index, type ->
            PyCallableParameterImpl.nonPsi("arg$index", type)
        }
        return PyCallableTypeImpl(parameters, returnType)
    }

    private fun lowerGeneric(
        expression: SageTypeExpression.Generic,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        bindings: Map<String, PyType> = emptyMap(),
    ): PyType? {
        val baseName = normalizeName(expression.base.qualifiedName)
        val arguments = expression.arguments.map { lower(it, anchor, context, query, bindings) ?: return null }
        if (baseName == "tuple") {
            if (arguments.isEmpty()) return null
            if (expression.arguments.lastOrNull() == SageTypeExpression.EllipsisType) {
                if (arguments.size != 2) return null
                return PyTupleType.createHomogeneous(anchor, arguments.first())
            }
            if (expression.arguments.any { it == SageTypeExpression.EllipsisType }) return null
            return PyTupleType.create(anchor, arguments)
        }
        if (expression.arguments.any { it == SageTypeExpression.EllipsisType }) return null
        val base = lowerName(baseName, anchor, query) as? PyClassType ?: return null
        return if (isBuiltinCollection(baseName)) {
            PyCollectionTypeImpl(base.pyClass, base.isDefinition, arguments)
        } else {
            PyClassTypeImpl(base.pyClass, base.isDefinition, arguments)
        }
    }

    private fun lowerLiteral(
        expression: SageTypeExpression.Literal,
        anchor: PsiElement,
        query: SageApiIndexQuery,
    ): PyType? {
        val lowered = expression.values.map { value ->
            when (value) {
                is com.starnotesxj.sagemath.sageapi.SageLiteralValue.StringValue ->
                    PyLiteralType.stringLiteral(anchor, value.value)
                is com.starnotesxj.sagemath.sageapi.SageLiteralValue.IntegerValue ->
                    value.value.toBigIntegerOrNull()?.let { PyLiteralType.intLiteral(anchor, it) }
                is com.starnotesxj.sagemath.sageapi.SageLiteralValue.BooleanValue ->
                    PyLiteralType.boolLiteral(anchor, value.value)
                com.starnotesxj.sagemath.sageapi.SageLiteralValue.NoneValue ->
                    PyBuiltinCache.getInstance(anchor).noneType
            }
        }
        if (lowered.any { it == null } || lowered.isEmpty()) return null
        return lowerUnionAtomically(lowered)
    }

    fun lowerTrustedReturn(
        signature: SageApiSignature,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyType? {
        val trusted = query.uniqueTrustedKnownReturnExpression(signature) ?: return null
        return lower(trusted, anchor, context, query)
    }

    /** Lower a known return contract without requiring call-argument binding. */
    fun lowerKnownReturn(
        signature: SageApiSignature,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyType? {
        if (signature.returnType.state != com.starnotesxj.sagemath.sageapi.SageTypeState.KNOWN ||
            signature.returnType.expression.isNullOrBlank()
        ) return null
        return lower(signature.returnType, anchor, context, query)
    }

    private fun lowerName(rawName: String, anchor: PsiElement, query: SageApiIndexQuery): PyType? {
        val name = normalizeName(rawName)
        if (name == "Any" || name == "typing.Any") return PyAnyType.Any
        if (name == "None") return PyBuiltinCache.getInstance(anchor).noneType
        if (name == "Ellipsis") return null
        // Do not ask PyBuiltinCache to resolve fully-qualified Sage names: in
        // a remote WSL SDK it can return an unresolved ``PyClassType``
        // placeholder, which would mask the canonical active-stub lookup and
        // erase all downstream member completion.  Python/builtin names still
        // use the platform cache normally.
        if (!name.startsWith("sage.")) {
            PyBuiltinCache.getInstance(anchor).getObjectType(name)?.let { return it }
        }
        val canonical = query.resolveKnownClassName(name) ?: name.takeIf { it.startsWith("sage.") } ?: return null
        val activeClass = SageStubIndex.findClassByCanonicalName(anchor.project, canonical)
            ?: return null
        val activeCanonical = SageStubIndex.canonicalQualifiedName(activeClass)
        if (activeCanonical != null && activeCanonical != canonical) return null
        return PyClassTypeImpl(activeClass, false)
    }

    private fun lowerUnion(types: List<PyType?>): PyType? {
        val known = types.filterNotNull().distinct()
        return when (known.size) {
            0 -> null
            1 -> known.single()
            else -> PyUnionType.union(known)
        }
    }

    private fun lowerUnionAtomically(types: List<PyType?>): PyType? {
        if (types.any { it == null }) return null
        return lowerUnion(types)
    }

    private fun isBuiltinCollection(name: String): Boolean = name in setOf(
        "list", "dict", "set", "tuple", "frozenset",
        "typing.List", "typing.Dict", "typing.Set", "typing.Tuple",
        "typing.Sequence", "typing.Mapping", "typing.Iterable",
        "collections.abc.Sequence", "collections.abc.Mapping", "collections.abc.Iterable",
    )

    private fun normalizeName(name: String): String = when (name) {
        "builtins.NoneType" -> "NoneType"
        "builtins.bool" -> "bool"
        "builtins.int" -> "int"
        "builtins.float" -> "float"
        "builtins.str" -> "str"
        "builtins.list" -> "list"
        "builtins.dict" -> "dict"
        "builtins.set" -> "set"
        "builtins.tuple" -> "tuple"
        "typing.List" -> "list"
        "typing.Dict" -> "dict"
        "typing.Set" -> "set"
        "typing.Tuple" -> "tuple"
        else -> name
    }
}
