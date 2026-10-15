package com.starnotesxj.sageide.type

import com.intellij.openapi.util.RecursionManager
import com.intellij.openapi.util.Ref
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiNamedElement
import com.jetbrains.python.ast.PyAstFunction
import com.jetbrains.python.psi.*
import com.jetbrains.python.psi.impl.PyBuiltinCache
import com.jetbrains.python.psi.types.*
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sagemath.sageapi.*

/**
 * Lowers index type expressions to the platform's real PyType graph.
 *
 * Index metadata is additive and may describe symbols absent from the active
 * interpreter stubs. Such symbols remain untyped here rather than becoming a
 * fabricated PSI class; completion/documentation can still use the index.
 */
object SageTypeLowering {
    private const val STORED_PARAMETER_TYPEVAR_PREFIX = "_SageStored"

    // PyCharm 2026.2 added generic arguments, variadic/signature-marker
    // factories, string defaults, and literal factories to Python's PSI API.
    // Keep these optional so the plugin remains binary-compatible with the
    // advertised 2026.1 minimum; reflection is cached and older releases fall
    // back to their equivalent non-generic/conservative representations.
    private val classTypeArgumentsMethod by lazy(LazyThreadSafetyMode.PUBLICATION) {
        PyClassType::class.java.methods.firstOrNull { it.name == "getTypeArguments" && it.parameterCount == 0 }
    }
    private val genericClassTypeConstructor by lazy(LazyThreadSafetyMode.PUBLICATION) {
        PyClassTypeImpl::class.java.constructors.firstOrNull { constructor ->
            val types = constructor.parameterTypes
            types.size == 3 && types[0] == PyClass::class.java &&
                types[1] == Boolean::class.javaPrimitiveType && List::class.java.isAssignableFrom(types[2])
        }
    }
    private val legacyCallableParameterConstructor by lazy(LazyThreadSafetyMode.PUBLICATION) {
        val booleanType = Boolean::class.javaPrimitiveType
        PyCallableParameterImpl::class.java.constructors.firstOrNull { constructor ->
            constructor.parameterTypes.contentEquals(
                arrayOf(
                    String::class.java,
                    Ref::class.java,
                    PyExpression::class.java,
                    PyParameter::class.java,
                    booleanType,
                    booleanType,
                    booleanType,
                    PsiElement::class.java,
                ),
            )
        }
    }
    private val callableParameterFactories by lazy(LazyThreadSafetyMode.PUBLICATION) {
        PyCallableParameterImpl.Companion::class.java.methods.associateBy { method ->
            method.name to method.parameterTypes.toList()
        }
    }
    private val literalFactories by lazy(LazyThreadSafetyMode.PUBLICATION) {
        PyLiteralType::class.java.methods.associateBy { method ->
            method.name to method.parameterTypes.toList()
        }
    }
    private val unionTypeFactory by lazy(LazyThreadSafetyMode.PUBLICATION) {
        val collectionParameter = arrayOf(Collection::class.java)
        PyUnionType::class.java.methods.firstOrNull {
            it.name == "unionOrNever" && it.parameterTypes.contentEquals(collectionParameter)
        } ?: PyUnionType::class.java.methods.firstOrNull {
            it.name == "union" && it.parameterTypes.contentEquals(collectionParameter)
        }
    }

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
            unionTypes(listOf(element, noneType))
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
                optionalCallableParameterFactory("positionalOnlySeparatorNonPsi")?.let(parameters::add)
                positionalOnlySeparatorAdded = true
            }
            if (parameter.keywordOnly && !keywordOnlySeparatorAdded) {
                optionalCallableParameterFactory("keywordOnlySeparatorNonPsi")?.let(parameters::add)
                keywordOnlySeparatorAdded = true
            }
            parameters += lowerParameter(parameter, anchor, context, query) ?: return null
        }
        if (hasPositionalOnly && !positionalOnlySeparatorAdded) {
            optionalCallableParameterFactory("positionalOnlySeparatorNonPsi")?.let(parameters::add)
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
        callSite: PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        callableQualifiedName: String? = null,
        callable: PyFunction? = null,
    ): List<SageApiSignature> {
        val arguments = callSite.getArguments(null)
        return signatures.mapNotNull { signature ->
            signatureBindings(signature, arguments, callSite, context, query, callableQualifiedName, callable)?.let { signature }
        }
    }

    fun lowerCallReturnType(
        signatures: List<SageApiSignature>,
        callSite: PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        callableQualifiedName: String? = null,
        callable: PyFunction? = null,
        receiverOverride: PyType? = null,
    ): PyType? {
        val arguments = callSite.getArguments(null)
        val viable = signatures.mapNotNull { signature ->
            signatureBindings(
                signature,
                arguments,
                callSite,
                context,
                query,
                callableQualifiedName,
                callable,
                receiverOverride,
            )?.let { signature to it }
        }
        if (viable.isEmpty()) return null

        /**
         * Several viable signatures are normally ambiguous.  Preserve that
         * fail-closed behavior when their parameter shapes are identical.  If
         * the contracts are distinct and every branch has a concrete indexed
         * return, however, their exact finite union is safe to publish.  This
         * is important for factories such as ``GF(11)`` whose generated
         * contract exposes backend branches and a fallback union: selecting a
         * public base would lose members such as ``multiplicative_order``.
         */
        val candidates = viable.mapNotNull { (signature, bindings) ->
            val names = signature.typeParameters.map { it.name }.toSet()
            val paramSpecNames = signature.typeParameters
                .filter { it.kind == SageApiTypeParameterKind.PARAM_SPEC }
                .map { it.name }
                .toSet()
            val expression = signature.returnType.expression?.let {
                SageTypeRefExpressionParser.parse(it, names, paramSpecNames)
            } ?: return@mapNotNull null
            val lowered = lower(expression, callSite, context, query, bindings)
                ?.takeUnless { it == PyAnyType.Any || it == PyAnyType.Unknown }
                ?: return@mapNotNull null
            signature to lowered
        }
        if (viable.size == 1) return candidates.singleOrNull()?.second
        if (candidates.size != viable.size) return null
        if (viable.map { signatureShape(it.first) }.distinct().size != viable.size) return null
        return unionTypes(candidates.map { it.second })
    }

    /** Parameter shape used only to distinguish true overload ambiguity. */
    private fun signatureShape(signature: SageApiSignature): String =
        signature.parameters.joinToString("|") { parameter ->
            listOf(
                parameter.name,
                parameter.type.state.name,
                parameter.type.expression.orEmpty(),
                parameter.defaultValue.orEmpty(),
                parameter.optional,
                parameter.keywordOnly,
                parameter.variadic,
                parameter.positionalOnly,
            ).joinToString("#")
        }

    private fun literalFallbackType(argument: PyExpression?): PyType? {
        return when (argument) {
            is PyNumericLiteralExpression -> {
                val cache = PyBuiltinCache.getInstance(argument)
                if (argument.isIntegerLiteral) cache.intType else cache.floatType
            }
            is PyStringLiteralExpression -> PyBuiltinCache.getInstance(argument).strType
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
        typeParameters: Map<String, SageApiTypeParameter>,
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
        val callee = call.callee as? PyReferenceExpression ?: return null
        val function = callee.reference.resolve() as? PyFunction
        val resolvedName = function?.let(::sageQualifiedName)
        val implicitName = if (resolvedName == null && callee.qualifier == null) {
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
        val name = (function as PsiNamedElement).name
        if (moduleName?.startsWith("sage.") == true && !name.isNullOrBlank()) {
            function.containingClass?.let { (it as PsiNamedElement).name }
                ?.takeIf { it.isNotBlank() }?.let { owner ->
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
        typeParameters: Map<String, SageApiTypeParameter>,
    ): Boolean {
        when (expected) {
            is SageTypeExpression.TypeVariable -> {
                val declaration = typeParameters[expected.name] ?: return false
                if (declaration.kind == SageApiTypeParameterKind.PARAM_SPEC) return false
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
                val actualArguments = genericTypeArguments(actualClass)
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
        callSite: PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        callableQualifiedName: String?,
        callable: PyFunction?,
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
        declaration: SageApiTypeParameter,
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
        callSite: PyCallSiteExpression,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
        callableQualifiedName: String?,
        callable: PyFunction?,
        receiverOverride: PyType? = null,
    ): Map<String, PyType>? {
        val typeParameters = signature.typeParameters.associateBy { it.name }
        if (typeParameters.values.any { it.kind == SageApiTypeParameterKind.PARAM_SPEC }) return null
        val bindings = linkedMapOf<String, PyType>()
        if (!bindGeneratedReceiverTypeVariables(
                signature = signature,
                callSite = callSite,
                context = context,
                anchor = callSite,
                query = query,
                bindings = bindings,
            )
        ) return null
        if (typeParameters.values.any { it.kind == SageApiTypeParameterKind.SELF }) {
            val selfType = receiverOverride
                ?: resolveSelfReceiver(callSite, context, query, callableQualifiedName, callable)
                ?: return null
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
                .filter { it.kind == SageApiTypeParameterKind.PARAM_SPEC }
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
            val keyword = (argument as? PyKeywordArgument)?.let { (it as PsiNamedElement).name }
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

    /**
     * Source contracts can prove that a getter returns the exact constructor
     * argument stored by its class.  The stub generator represents that fact
     * as ``class C(Generic[_SageStored...])``.  Unlike an ordinary generic
     * function, such a getter has no value argument from which to bind its
     * type variable, so bind it from the concrete receiver's type arguments.
     *
     * This deliberately recognizes only the private type-variable names
     * emitted by our generator.  Other generic bases may be dynamic or use a
     * different scope/order, and therefore remain unresolved here instead of
     * being positionally guessed.
     */
    private fun bindGeneratedReceiverTypeVariables(
        signature: SageApiSignature,
        callSite: PyCallSiteExpression,
        context: TypeEvalContext,
        anchor: PsiElement,
        query: SageApiIndexQuery,
        bindings: MutableMap<String, PyType>,
    ): Boolean {
        val declared = signature.typeParameters.associateBy { it.name }
        if (declared.keys.none { it.startsWith(STORED_PARAMETER_TYPEVAR_PREFIX) }) return true
        val call = callSite as? PyCallExpression ?: return true
        val callee = call.callee as? PyQualifiedExpression ?: return true
        val receiver = callee.qualifier ?: return true
        val receiverType = context.getType(receiver) as? PyClassType ?: return true
        if (receiverType.isDefinition) return true
        val actualArguments = genericTypeArguments(receiverType)
        if (actualArguments.isEmpty()) return true
        val genericExpression = receiverType.pyClass.superClassExpressions.singleOrNull { expression ->
            expression.text.removePrefix("typing.").startsWith("Generic[")
        } ?: return true
        val genericText = genericExpression.text.removePrefix("typing.")
        val formalArguments = genericText
            .removePrefix("Generic[")
            .removeSuffix("]")
            .split(',')
            .map(String::trim)
        if (formalArguments.isEmpty() || formalArguments.size != actualArguments.size) return true
        if (formalArguments.any { !it.startsWith(STORED_PARAMETER_TYPEVAR_PREFIX) }) return true
        for ((formal, actual) in formalArguments.zip(actualArguments)) {
            val declaration = declared[formal] ?: continue
            if (actual == PyAnyType.Any || actual == PyAnyType.Unknown) return false
            if (!typeParameterAccepts(declaration, actual, context, anchor, query)) return false
            val previous = bindings[formal]
            if (previous == null) {
                bindings[formal] = actual
            } else if (!PyTypeChecker.match(previous, actual, context) || !PyTypeChecker.match(actual, previous, context)) {
                return false
            }
        }
        return true
    }

    private fun signatureAcceptsCall(
        signature: SageApiSignature,
        arguments: List<PyExpression>,
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
            if (argument is PyStarArgument) return false
            val keyword = (argument as? PyKeywordArgument)?.let { (it as PsiNamedElement).name }
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
        expression: PyExpression?,
        expected: SageTypeRef,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): Boolean {
        if (expression == null || expected.state != SageTypeState.KNOWN) return true
        val literalName = when (expression) {
            is PyNumericLiteralExpression ->
                if (expression.isIntegerLiteral) "int" else "float"
            is PyStringLiteralExpression -> "str"
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
        val literalType = (expression as? PyNumericLiteralExpression)?.let {
                if (it.isIntegerLiteral) PyBuiltinCache.getInstance(expression).intType else PyBuiltinCache.getInstance(expression).floatType
            }
            ?: (expression as? PyStringLiteralExpression)?.let {
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
                actual is PyAnyType ||
                expectedType is PyAnyType ||
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
            val factory = if (parameter.keywordOnly) "keywordContainerNonPsi" else "positionalContainerNonPsi"
            return optionalCallableParameterFactory(factory, parameter.name, type)
                ?: legacyVariadicParameter(parameter.name, type, parameter.keywordOnly, anchor)
        }
        val defaultValue = parameter.defaultValue
        if (defaultValue != null) {
            optionalCallableParameterFactory("nonPsi", parameter.name, type, defaultValue)?.let { return it }
        }
        return PyCallableParameterImpl.nonPsi(parameter.name, type)
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
        if (baseName == "sage.type_contracts.ParentElement" || baseName == "ParentElement") {
            val parent = bindings["Self"] as? PyClassType ?: return null
            return lowerParentElement(parent, anchor, context, query)
        }
        // Relation-aware contracts are used when a method returns an element
        // of a parent reached through the receiver (for example a morphism's
        // codomain or an element's base ring).  Resolve that parent first,
        // then apply the same concrete element-factory proof as
        // ``ParentElement[Self]``.  A missing/ambiguous relation is kept
        // unresolved instead of leaking a public Element base or Any.
        val relatedRelation = when (baseName) {
            "sage.type_contracts.CodomainElement", "CodomainElement" -> "codomain"
            "sage.type_contracts.DomainElement", "DomainElement" -> "domain"
            "sage.type_contracts.BaseRingElement", "BaseRingElement" -> "base_ring"
            "sage.type_contracts.BaseFieldElement", "BaseFieldElement" -> "base_field"
            "sage.type_contracts.AmbientElement", "AmbientElement" -> "ambient"
            "sage.type_contracts.ResidueRingElement", "ResidueRingElement" -> "residue_ring"
            "sage.type_contracts.ResidueFieldElement", "ResidueFieldElement" -> "residue_field"
            "sage.type_contracts.WeightLatticeElement", "WeightLatticeElement" -> "weight_lattice_realization"
            "sage.type_contracts.MessageSpaceElement", "MessageSpaceElement" -> "message_space"
            "sage.type_contracts.InputSpaceElement", "InputSpaceElement" -> "input_space"
            "sage.type_contracts.CoefficientRingElement", "CoefficientRingElement" -> "coefficient_ring"
            "sage.type_contracts.FreeModuleElement", "FreeModuleElement" -> "free_module"
            "sage.type_contracts.FunctionFieldElement", "FunctionFieldElement" -> "function_field"
            "sage.type_contracts.GroupElement", "GroupElement" -> "group"
            "sage.type_contracts.LatticeElement", "LatticeElement" -> "lattice"
            "sage.type_contracts.ModuleElement", "ModuleElement" -> "module"
            "sage.type_contracts.IdealElement", "IdealElement" -> "ideal"
            "sage.type_contracts.CurveElement", "CurveElement" -> "curve"
            else -> null
        }
        if (relatedRelation != null) {
            val receiver = bindings["Self"] as? PyClassType ?: return null
            return lowerRelatedParentElement(receiver, relatedRelation, anchor, context, query)
        }
        // Parent-returning relation contracts describe the concrete parent
        // object reached through the receiver (for example ``f.base_ring()``
        // or ``m.domain()``).  They are intentionally separate from the
        // ``*Element[Self]`` contracts above: lowering first resolves the
        // receiver's exact accessor result and only then exposes that parent
        // class to completion/documentation.
        val relatedParent = when (baseName) {
            "sage.type_contracts.Parent", "Parent" -> "parent"
            "sage.type_contracts.BaseRing", "BaseRing" -> "base_ring"
            "sage.type_contracts.BaseField", "BaseField" -> "base_field"
            "sage.type_contracts.Domain", "Domain" -> "domain"
            "sage.type_contracts.Codomain", "Codomain" -> "codomain"
            "sage.type_contracts.Ambient", "Ambient" -> "ambient"
            "sage.type_contracts.BaseScheme", "BaseScheme" -> "base_scheme"
            "sage.type_contracts.BaseSpace", "BaseSpace" -> "base_space"
            "sage.type_contracts.ValueGroup", "ValueGroup" -> "value_group"
            "sage.type_contracts.ValueSemigroup", "ValueSemigroup" -> "value_semigroup"
            "sage.type_contracts.ResidueRing", "ResidueRing" -> "residue_ring"
            "sage.type_contracts.ResidueField", "ResidueField" -> "residue_field"
            "sage.type_contracts.Group", "Group" -> "group"
            "sage.type_contracts.Lattice", "Lattice" -> "lattice"
            "sage.type_contracts.Module", "Module" -> "module"
            "sage.type_contracts.FreeModule", "FreeModule" -> "free_module"
            "sage.type_contracts.MessageSpace", "MessageSpace" -> "message_space"
            "sage.type_contracts.InputSpace", "InputSpace" -> "input_space"
            "sage.type_contracts.CoefficientRing", "CoefficientRing" -> "coefficient_ring"
            "sage.type_contracts.FunctionField", "FunctionField" -> "function_field"
            "sage.type_contracts.Curve", "Curve" -> "curve"
            "sage.type_contracts.Ideal", "Ideal" -> "ideal"
            else -> null
        }
        if (relatedParent != null) {
            val receiver = bindings["Self"] as? PyClassType ?: return null
            return lowerRelatedParent(receiver, relatedParent, anchor, context, query)
        }
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
            genericClassType(base, arguments)
        }
    }

    /**
     * Resolve the symbolic parent/element contract against one concrete
     * receiver.  Sage parents choose their element class at runtime, so a
     * shared ``Element`` base would lose the methods users actually need.  We
     * instead inspect the receiver's indexed element-producing protocols and
     * accept a result only when every concrete proof agrees.
     */
    private fun lowerParentElement(
        parent: PyClassType,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyType? {
        val owner = SageStubIndex.canonicalQualifiedName(parent.pyClass) ?: return null
        if (!owner.startsWith("sage.")) return null
        val protocolNames = listOf(
            "__call__",
            "_element_constructor_",
            "an_element",
            "_an_element_",
            "from_vector",
            "from_coordinates",
            "retract",
            "gen",
            "zero",
            "one",
            "identity",
            "unit",
            "random_element",
        )
        val concreteResults = protocolNames
            .flatMap { name -> query.members(owner, name) }
            .filter { it.kind == SageApiSymbolKind.METHOD && it.signatures.isNotEmpty() }
            .flatMap { entry ->
                entry.signatures.mapNotNull { signature ->
                    if (signature.returnType.state != SageTypeState.KNOWN ||
                        signature.returnType.expression.isNullOrBlank()
                    ) return@mapNotNull null
                    val typeNames = signature.typeParameters.map { it.name }.toSet()
                    val paramSpecNames = signature.typeParameters
                        .filter { it.kind == SageApiTypeParameterKind.PARAM_SPEC }
                        .map { it.name }
                        .toSet()
                    val parsed = SageTypeRefExpressionParser.parse(
                        signature.returnType.expression!!,
                        typeNames,
                        paramSpecNames,
                    ) ?: return@mapNotNull null
                    if (containsParentElementContract(parsed)) return@mapNotNull null
                    val lowered = lower(parsed, anchor, context, query, mapOf("Self" to parent))
                        ?: return@mapNotNull null
                    // A receiver-preserving result is not evidence of an
                    // element class; it would merely recurse back to Parent.
                    if (lowered is PyClassType &&
                        SageStubIndex.canonicalQualifiedName(lowered.pyClass) == owner
                    ) return@mapNotNull null
                    lowered
                }
            }
            .distinct()
        concreteResults.singleOrNull()?.let { return it }

        // Dynamic interpreter interfaces follow a stable module-level naming
        // convention even when their implementation methods are inherited
        // and therefore absent from the concrete stub.  Resolve only the
        // matching ``sage.interfaces.<backend>`` wrapper; never apply this
        // heuristic to ordinary mathematical parents.
        if (owner.contains(".interfaces.")) {
            val module = owner.substringBeforeLast('.')
            val elementName = owner.substringAfterLast('.') + "Element"
            val canonical = query.resolveKnownClassName("$module.$elementName")
                ?: return null
            val activeClass = SageStubIndex.findClassByCanonicalName(anchor.project, canonical)
                ?: return null
            val activeCanonical = SageStubIndex.canonicalQualifiedName(activeClass)
            if (activeCanonical == canonical) return PyClassTypeImpl(activeClass, false)
        }
        return null
    }

    /** Resolve a concrete element class through one receiver relation. */
    private fun lowerRelatedParentElement(
        receiver: PyClassType,
        relationName: String,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyType? {
        val owner = SageStubIndex.canonicalQualifiedName(receiver.pyClass) ?: return null
        val relatedParents = query.members(owner, relationName)
            .asSequence()
            .filter { it.kind == SageApiSymbolKind.METHOD || it.kind == SageApiSymbolKind.PROPERTY }
            .flatMap { entry -> entry.signatures.asSequence() }
            .mapNotNull { signature ->
                if (signature.returnType.state != SageTypeState.KNOWN ||
                    signature.returnType.expression.isNullOrBlank()
                ) return@mapNotNull null
                val typeNames = signature.typeParameters.map { it.name }.toSet()
                val paramSpecNames = signature.typeParameters
                    .filter { it.kind == SageApiTypeParameterKind.PARAM_SPEC }
                    .map { it.name }
                    .toSet()
                val parsed = SageTypeRefExpressionParser.parse(
                    signature.returnType.expression!!,
                    typeNames,
                    paramSpecNames,
                ) ?: return@mapNotNull null
                lower(parsed, anchor, context, query, mapOf("Self" to receiver)) as? PyClassType
            }
            .distinctBy {
                SageStubIndex.canonicalQualifiedName(it.pyClass) ?: (it.pyClass as PsiNamedElement).name
            }
            .toList()
        val parent = relatedParents.singleOrNull() ?: return null
        return lowerParentElement(parent, anchor, context, query)
    }

    /** Resolve a concrete parent object through one receiver relation. */
    private fun lowerRelatedParent(
        receiver: PyClassType,
        relationName: String,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyType? {
        val owner = SageStubIndex.canonicalQualifiedName(receiver.pyClass) ?: return null
        val relationContractNames = setOf(
            "sage.type_contracts.Parent", "Parent",
            "sage.type_contracts.BaseRing", "BaseRing",
            "sage.type_contracts.BaseField", "BaseField",
            "sage.type_contracts.Domain", "Domain",
            "sage.type_contracts.Codomain", "Codomain",
            "sage.type_contracts.Ambient", "Ambient",
            "sage.type_contracts.BaseScheme", "BaseScheme",
            "sage.type_contracts.BaseSpace", "BaseSpace",
            "sage.type_contracts.ValueGroup", "ValueGroup",
            "sage.type_contracts.ValueSemigroup", "ValueSemigroup",
            "sage.type_contracts.ResidueRing", "ResidueRing",
            "sage.type_contracts.ResidueField", "ResidueField",
            "sage.type_contracts.ResidueRingElement", "ResidueRingElement",
            "sage.type_contracts.ResidueFieldElement", "ResidueFieldElement",
            "sage.type_contracts.WeightLatticeElement", "WeightLatticeElement",
            "sage.type_contracts.DomainElement", "DomainElement",
            "sage.type_contracts.Group", "Group",
            "sage.type_contracts.Lattice", "Lattice",
            "sage.type_contracts.Module", "Module",
            "sage.type_contracts.FreeModule", "FreeModule",
            "sage.type_contracts.MessageSpace", "MessageSpace",
            "sage.type_contracts.InputSpace", "InputSpace",
            "sage.type_contracts.CoefficientRing", "CoefficientRing",
            "sage.type_contracts.FunctionField", "FunctionField",
            "sage.type_contracts.Curve", "Curve",
            "sage.type_contracts.Ideal", "Ideal",
            "sage.type_contracts.MessageSpaceElement", "MessageSpaceElement",
            "sage.type_contracts.InputSpaceElement", "InputSpaceElement",
            "sage.type_contracts.CoefficientRingElement", "CoefficientRingElement",
            "sage.type_contracts.FreeModuleElement", "FreeModuleElement",
            "sage.type_contracts.FunctionFieldElement", "FunctionFieldElement",
            "sage.type_contracts.GroupElement", "GroupElement",
            "sage.type_contracts.LatticeElement", "LatticeElement",
            "sage.type_contracts.ModuleElement", "ModuleElement",
            "sage.type_contracts.IdealElement", "IdealElement",
            "sage.type_contracts.CurveElement", "CurveElement",
        )
        val concreteParents = query.members(owner, relationName)
            .asSequence()
            .filter { it.kind == SageApiSymbolKind.METHOD || it.kind == SageApiSymbolKind.PROPERTY }
            .flatMap { it.signatures.asSequence() }
            .mapNotNull { signature ->
                if (signature.returnType.state != SageTypeState.KNOWN ||
                    signature.returnType.expression.isNullOrBlank()
                ) return@mapNotNull null
                val typeNames = signature.typeParameters.map { it.name }.toSet()
                val paramSpecNames = signature.typeParameters
                    .filter { it.kind == SageApiTypeParameterKind.PARAM_SPEC }
                    .map { it.name }
                    .toSet()
                val parsed = SageTypeRefExpressionParser.parse(
                    signature.returnType.expression!!,
                    typeNames,
                    paramSpecNames,
                ) ?: return@mapNotNull null
                if (parsed is SageTypeExpression.Generic &&
                    normalizeName(parsed.base.qualifiedName) in relationContractNames
                ) return@mapNotNull null
                lower(parsed, anchor, context, query, mapOf("Self" to receiver))
            }
            .filterNot { it is PyAnyType }
            .distinctBy { type ->
                (type as? PyClassType)?.let { SageStubIndex.canonicalQualifiedName(it.pyClass) }
                    ?: type.toString()
            }
            .toList()
        return concreteParents.singleOrNull()
    }

    private fun containsParentElementContract(expression: SageTypeExpression): Boolean = when (expression) {
        is SageTypeExpression.Generic ->
            expression.base.qualifiedName == "sage.type_contracts.ParentElement" ||
                expression.base.qualifiedName == "ParentElement" ||
                expression.arguments.any(::containsParentElementContract)
        is SageTypeExpression.Union -> expression.members.any(::containsParentElementContract)
        is SageTypeExpression.Optional -> containsParentElementContract(expression.element)
        is SageTypeExpression.Callable ->
            (expression.parameters?.any(::containsParentElementContract) == true) ||
                containsParentElementContract(expression.returnType)
        else -> false
    }

    private fun lowerLiteral(
        expression: SageTypeExpression.Literal,
        anchor: PsiElement,
        query: SageApiIndexQuery,
    ): PyType? {
        val lowered = expression.values.map { value ->
            when (value) {
                is SageLiteralValue.StringValue ->
                    literalFactory("stringLiteral", arrayOf(PsiElement::class.java, String::class.java), anchor, value.value)
                        ?: PyBuiltinCache.getInstance(anchor).strType
                is SageLiteralValue.IntegerValue ->
                    value.value.toBigIntegerOrNull()?.let { integer ->
                        literalFactory(
                            "intLiteral",
                            arrayOf(PsiElement::class.java, java.math.BigInteger::class.java),
                            anchor,
                            integer,
                        ) ?: PyBuiltinCache.getInstance(anchor).intType
                    }
                is SageLiteralValue.BooleanValue ->
                    literalFactory(
                        "boolLiteral",
                        arrayOf(PsiElement::class.java, Boolean::class.javaPrimitiveType!!),
                        anchor,
                        value.value,
                    ) ?: PyBuiltinCache.getInstance(anchor).boolType
                SageLiteralValue.NoneValue ->
                    PyBuiltinCache.getInstance(anchor).noneType
            }
        }
        if (lowered.any { it == null } || lowered.isEmpty()) return null
        return lowerUnionAtomically(lowered)
    }

    private fun genericTypeArguments(type: PyClassType): List<PyType> = runCatching {
        (classTypeArgumentsMethod?.invoke(type) as? List<*>)?.filterIsInstance<PyType>().orEmpty()
    }.getOrDefault(emptyList())

    private fun genericClassType(base: PyClassType, arguments: List<PyType>): PyClassType {
        val constructor = genericClassTypeConstructor ?: return PyClassTypeImpl(base.pyClass, base.isDefinition)
        return runCatching {
            constructor.newInstance(base.pyClass, base.isDefinition, arguments) as PyClassType
        }.getOrDefault(PyClassTypeImpl(base.pyClass, base.isDefinition))
    }

    private fun legacyVariadicParameter(
        name: String,
        type: PyType,
        keywordOnly: Boolean,
        anchor: PsiElement,
    ): PyCallableParameter? {
        val constructor = legacyCallableParameterConstructor ?: return null
        return runCatching {
            constructor.newInstance(
                *arrayOf<Any?>(
                    name,
                    Ref.create(type),
                    null,
                    null,
                    !keywordOnly,
                    keywordOnly,
                    false,
                    anchor,
                ),
            ) as? PyCallableParameter
        }.getOrNull()
    }

    private fun optionalCallableParameterFactory(name: String, vararg arguments: Any): PyCallableParameter? {
        val parameterTypes = when (arguments.size) {
            0 -> emptyList()
            2 -> listOf(String::class.java, PyType::class.java)
            3 -> listOf(String::class.java, PyType::class.java, String::class.java)
            else -> return null
        }
        val factory = callableParameterFactories[name to parameterTypes] ?: return null
        return runCatching {
            factory.invoke(PyCallableParameterImpl.Companion, *arguments) as? PyCallableParameter
        }.getOrNull()
    }

    private fun literalFactory(
        name: String,
        parameterTypes: Array<Class<*>>,
        anchor: PsiElement,
        value: Any,
    ): PyType? {
        val factory = literalFactories[name to parameterTypes.toList()] ?: return null
        return runCatching { factory.invoke(null, anchor, value) as? PyType }.getOrNull()
    }

    /** Lower a known return contract without requiring call-argument binding. */
    fun lowerKnownReturn(
        signature: SageApiSignature,
        anchor: PsiElement,
        context: TypeEvalContext,
        query: SageApiIndexQuery,
    ): PyType? {
        if (signature.returnType.state != SageTypeState.KNOWN ||
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
            else -> unionTypes(known)
        }
    }

    internal fun unionTypes(types: List<PyType>): PyType? {
        val distinct = types.distinct()
        if (distinct.isEmpty()) return null
        val factory = unionTypeFactory ?: return null
        return runCatching { factory.invoke(null, distinct) as? PyType }.getOrNull()
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
