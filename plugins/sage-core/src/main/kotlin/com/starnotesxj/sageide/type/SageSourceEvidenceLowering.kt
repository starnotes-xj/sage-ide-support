package com.starnotesxj.sageide.type

import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.util.RecursionManager
import com.intellij.openapi.util.Ref
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiInvalidElementAccessException
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyBinaryExpression
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyListLiteralExpression
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyReturnStatement
import com.jetbrains.python.psi.PyStatement
import com.jetbrains.python.psi.PySubscriptionExpression
import com.jetbrains.python.psi.PyForPart
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.PyAnyType
import com.jetbrains.python.psi.types.PyCallableType
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyClassTypeImpl
import com.jetbrains.python.psi.types.PyCollectionTypeImpl
import com.jetbrains.python.psi.types.PyType
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex

/**
 * Carries concrete Python PSI types across Sage assignment targets using
 * source-level evidence, as the last fallback after the indexed contracts.
 *
 * The Sage API index answers factory/call/operator contracts from curated
 * data; this lowering covers the shapes the index cannot see and that the
 * generated stubs leave unannotated:
 *
 * - `values = {}` followed by `values[name] = Integer(...)` writes: every
 *   same-scope write agreeing on one concrete class proves the container's
 *   value type, so `N, e, c = values[...]` and `x = values[k]` unpack and
 *   read targets get that class;
 * - `for x in <iterable>`: the loop target gets the iterable's concrete
 *   element type when a `list[T]`-style type argument is provable;
 * - an unqualified Sage constructor call whose name Python cannot resolve
 *   (`Integer(13)` under the implicit sage.all namespace) resolves through
 *   the Sage SDK stub tree only;
 * - a Sage SDK method without a stub annotation may still be understood
 *   from its sibling `.py` implementation when every return branch agrees.
 *
 * UNKNOWN, DYNAMIC, union, and ambiguous results are never answered — the
 * caller falls back to Python's own inference. Everything here runs only
 * inside `.sage` files; native concrete types stay authoritative.
 */
internal object SageSourceEvidenceLowering {

    fun assignedConcreteType(target: PyTargetExpression, context: com.jetbrains.python.psi.types.TypeEvalContext): Ref<PyType>? {
        if (!target.isValid) return null
        return try {
            if (DumbService.isDumb(target.project)) return null
            val assignedType = RecursionManager.doPreventingRecursion(target, true) {
                ProgressManager.checkCanceled()
                forLoopElementType(target, context, 0) ?: run {
                    val assigned = target.findAssignedValue()?.takeIf { it.isValid } ?: return@run null
                    // `N, e = values['N'], values['e']`: a tuple-unpacking target
                    // reports the WHOLE RHS tuple; the same-position element is
                    // the target's own assigned value.
                    val effective = assignedElementForTarget(target, assigned) ?: return@run null
                    // A native dict[Any] over `values['N']` is not a usable
                    // answer: only a CONCRETE native class type short-circuits
                    // the source-evidence derivation below.
                    val nativeType = context.getType(effective)
                    if (nativeType is PyClassType && isConcreteClassType(nativeType)) nativeType
                    else sourceExpressionType(target, effective, context, 0) ?: nativeType
                }
            } ?: return null
            val classType = assignedType as? PyClassType ?: return null
            if (!isConcreteClassType(classType)) return null
            Ref.create(classType)
        } catch (_: PsiInvalidElementAccessException) {
            // Type queries can race with PSI invalidation while resolving the
            // assignment or its class. Leave stale results to Python's normal
            // fallback path instead of turning them into a definite Sage type.
            null
        }
    }

    /**
     * The expression assigned to *target* specifically. Plain assignments
     * answer their RHS; tuple-unpacking targets answer the same-position
     * element of the RHS tuple (or null when the shapes do not line up
     * one-to-one, including starred targets).
     */
    private fun assignedElementForTarget(
        target: PyTargetExpression,
        assigned: com.jetbrains.python.psi.PyExpression,
    ): com.jetbrains.python.psi.PyExpression? {
        if (assigned !is com.jetbrains.python.psi.PyTupleExpression) return assigned
        val targetTuple = target.parent as? com.jetbrains.python.psi.PyTupleExpression ?: return null
        val index = targetTuple.elements.indexOf(target)
        if (index < 0 || targetTuple.elements.size != assigned.elements.size) return null
        if (targetTuple.elements.any { it is com.jetbrains.python.psi.PyStarExpression }) return null
        return assigned.elements.getOrNull(index)
    }

    /**
     * Extends Python PSI only inside Sage files and only with evidence from
     * Sage SDK methods. Native concrete types remain authoritative; source
     * return analysis is accepted only when every return resolves to the same
     * concrete class type.
     */
    private fun sourceExpressionType(
        sageTarget: PyTargetExpression,
        expression: com.jetbrains.python.psi.PyExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyType? {
        if (depth > MAX_SOURCE_TYPE_DEPTH || !expression.isValid) return null
        if (!SageFileUtils.isSageFile(sageTarget.containingFile)) return null

        return try {
            RecursionManager.doPreventingRecursion(expression, true) {
                ProgressManager.checkCanceled()
                val nativeType = context.getType(expression)
                if (nativeType is PyClassType && isConcreteClassType(nativeType)) {
                    return@doPreventingRecursion nativeType
                }
                val inferred = when (expression) {
                    is PyCallExpression -> sourceCallType(sageTarget, expression, context, depth + 1)
                    is PyListLiteralExpression -> listLiteralType(sageTarget, expression, context, depth + 1)
                    is PySubscriptionExpression -> subscriptionElementType(sageTarget, expression, context, depth + 1)
                    is PyBinaryExpression -> binaryOperatorType(sageTarget, expression, context, depth + 1)
                    is PyReferenceExpression -> assignedReferenceType(sageTarget, expression, context, depth + 1)
                    else -> null
                }
                inferred ?: nativeType
            }
        } catch (_: PsiInvalidElementAccessException) {
            null
        }
    }

    private fun sourceCallType(
        sageTarget: PyTargetExpression,
        call: PyCallExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyType? {
        val nativeType = context.getType(call)
        val callee = call.callee as? PyReferenceExpression ?: return nativeType
        val qualifier = callee.qualifier
        if (qualifier == null) {
            unresolvedSageClassCallType(sageTarget, callee)?.let { return it }
            // A bare constructor call may resolve to the Sage stub class and
            // still type as null: the generated stubs carry no __init__/__new__
            // metadata for many classes. The resolved Sage stub class itself
            // is then the only sound instance type for the call.
            val resolvedClass = callee.reference.multiResolve(false)
                .mapNotNull { it.element as? com.jetbrains.python.psi.PyClass }
                .singleOrNull()
            if (resolvedClass != null && SageStubIndex.isSageStubFile(resolvedClass.containingFile)) {
                return PyClassTypeImpl(resolvedClass, false)
            }
            return nativeType
        }
        val receiverType = sourceExpressionType(sageTarget, qualifier, context, depth + 1) as? PyClassType ?: return nativeType
        val methodName = callee.name ?: return nativeType
        val declaration = receiverType.pyClass.findMethodByName(methodName, true, context) ?: return nativeType
        val sourceMethod = sageSourceImplementation(declaration) ?: return nativeType
        if (sourceMethod.isGenerator) return nativeType
        if (declaration.annotation != null) return nativeType

        val sourceFile = sourceMethod.containingFile.takeIf { it.isValid } ?: return nativeType
        val sourceContext = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(sageTarget.project, sourceFile)
        return sourceReturnType(sourceMethod, sourceContext, sageTarget, depth + 1) ?: nativeType
    }

    /** Resolves Sage's implicit `.sage` class constructors when Python leaves their name unresolved. */
    private fun unresolvedSageClassCallType(
        sageTarget: PyTargetExpression,
        callee: PyReferenceExpression,
    ): PyClassType? {
        if (!SageFileUtils.isSageFile(sageTarget.containingFile) ||
            callee.reference.multiResolve(false).any { it.element != null }
        ) return null
        val name = callee.name ?: return null
        val pyClass = SageStubIndex.findClass(sageTarget.project, name) ?: return null
        if (!SageStubIndex.isSageSdkFile(pyClass.containingFile)) return null
        return PyClassTypeImpl(pyClass, false)
    }

    private fun sourceReturnType(
        function: PyFunction,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        sageTarget: PyTargetExpression,
        depth: Int,
    ): PyType? {
        if (!returnsValueOnEveryPath(function.statementList.statements)) return null
        val returns = PsiTreeUtil.findChildrenOfType(function, PyReturnStatement::class.java)
            .filter { PsiTreeUtil.getParentOfType(it, PyFunction::class.java) === function }
        if (returns.isEmpty()) return null
        val types = returns.map { statement ->
            val expression = statement.expression ?: return null
            sourceExpressionType(sageTarget, expression, context, depth + 1) ?: return null
        }
        return sameConcreteReturnType(types)
    }

    private fun subscriptionElementType(
        sageTarget: PyTargetExpression,
        expression: PySubscriptionExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyType? {
        val collection = sourceExpressionType(sageTarget, expression.operand, context, depth + 1) as? PyClassType
        if (collection != null) {
            if (collection.pyClass.findMethodByName("__getitem__", true, context) == null) return null
            val elementType = collection.typeArguments.singleOrNull() as? PyClassType
            if (elementType != null && isConcreteClassType(elementType)) return elementType
            if (collection.pyClass.name != "dict") return null
            // `values = {}` types as dict[K, Any] (or unparameterized): the
            // Any value slot is an unknown the write proof below may narrow;
            // any other non-concrete declared value type is final.
            val declaredValue = collection.typeArguments.getOrNull(1)
            if (declaredValue != null && declaredValue !is PyAnyType &&
                !(declaredValue is PyClassType && isConcreteClassType(declaredValue))
            ) return null
        }
        return dictionaryWriteValueType(sageTarget, expression, context, depth + 1)
    }

    /** Infers a Sage dictionary subscript only when every same-scope write agrees. */
    private fun dictionaryWriteValueType(
        sageTarget: PyTargetExpression,
        subscription: PySubscriptionExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyClassType? {
        val containerReference = subscription.operand as? PyReferenceExpression ?: return null
        val containerTargets = containerReference.reference.multiResolve(false)
            .mapNotNull { it.element as? PyTargetExpression }
            .distinct()
        val containerTarget = containerTargets.singleOrNull() ?: return null
        if (containerTarget.annotationValue != null || containerTarget.findAssignedValue() !is com.jetbrains.python.psi.PyDictLiteralExpression) return null

        val scope = assignmentScope(containerTarget)
        val writeTypes = mutableListOf<PyClassType>()
        for (assignment in PsiTreeUtil.findChildrenOfType(sageTarget.containingFile, PyAssignmentStatement::class.java)) {
            ProgressManager.checkCanceled()
            if (assignmentScope(assignment) !== scope) continue
            val writesToContainer = assignment.targets.filterIsInstance<PySubscriptionExpression>().any { target ->
                val reference = target.operand as? PyReferenceExpression ?: return@any false
                val targets = reference.reference.multiResolve(false)
                    .mapNotNull { it.element as? PyTargetExpression }
                    .distinct()
                targets.size == 1 && targets.single() === containerTarget
            }
            if (!writesToContainer) continue
            val value = assignment.assignedValue?.takeIf { it.isValid } ?: return null
            val valueType = sourceExpressionType(sageTarget, value, context, depth + 1) as? PyClassType ?: return null
            if (!isConcreteClassType(valueType)) return null
            writeTypes += valueType
        }
        return sameConcreteReturnType(writeTypes)
    }

    private fun assignmentScope(element: PsiElement): PsiElement {
        PsiTreeUtil.getParentOfType(element, PyFunction::class.java, false)?.let { return it }
        PsiTreeUtil.getParentOfType(element, com.jetbrains.python.psi.PyClass::class.java, false)?.let { return it }
        return element.containingFile
    }

    /** Lowers a simple Sage `for name in iterable` target to the iterable item type. */
    private fun forLoopElementType(
        target: PyTargetExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyClassType? {
        val forPart = PsiTreeUtil.getParentOfType(target, PyForPart::class.java, false) ?: return null
        if (forPart.target !== target) return null
        val iterable = forPart.source ?: return null
        return iterableElementType(target, iterable, context, depth + 1)
    }

    private fun iterableElementType(
        sageTarget: PyTargetExpression,
        iterable: com.jetbrains.python.psi.PyExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyClassType? {
        // A list literal's element type is its elements' unanimous concrete
        // type — constructing a builtins.list generic is unnecessary (and can
        // fail outright in a Sage dialect file without a Python SDK scope).
        // Follow a plain reference to its assigned literal WITHOUT asking the
        // type engine: computing the reference's native type here re-enters
        // the container target's own derivation still on the stack.
        val effectiveIterable = if (iterable is PyReferenceExpression && iterable.qualifier == null) {
            iterable.reference.multiResolve(false)
                .mapNotNull { it.element as? PyTargetExpression }
                .singleOrNull()
                ?.findAssignedValue() as? PyListLiteralExpression
                ?: iterable
        } else {
            iterable
        }
        if (effectiveIterable is PyListLiteralExpression) {
            val elements = effectiveIterable.elements
            if (elements.isEmpty()) return null
            val elementTypes = elements.map { element ->
                sourceExpressionType(sageTarget, element, context, depth + 1) as? PyClassType ?: return null
            }
            return sameConcreteReturnType(elementTypes)
        }
        val iterableType = sourceExpressionType(sageTarget, iterable, context, depth + 1) as? PyClassType ?: return null
        val elementType = iterableType.typeArguments.singleOrNull() as? PyClassType ?: return null
        if (!isConcreteClassType(elementType)) return null
        if (iterableType.pyClass.findMethodByName("__iter__", true, context) == null &&
            iterableType.pyClass.findMethodByName("__getitem__", true, context) == null
        ) return null
        return elementType
    }

    private fun listLiteralType(
        sageTarget: PyTargetExpression,
        expression: PyListLiteralExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyClassType? {
        val elements = expression.elements
        if (elements.isEmpty()) return null
        val elementTypes = elements.map { element ->
            sourceExpressionType(sageTarget, element, context, depth + 1) as? PyClassType ?: return null
        }
        val elementType = elementTypes.first()
        if (elementTypes.any { !sameConcreteClassType(elementType, it) }) return null

        val collectionType = PyCollectionTypeImpl.createTypeByQName(
            expression,
            "builtins.list",
            false,
            listOf(elementType),
        ) ?: PyCollectionTypeImpl.createTypeByQName(expression, "list", false, listOf(elementType)) ?: return null
        val resolvedElementType = collectionType.typeArguments.singleOrNull() as? PyClassType ?: return null
        if (!sameConcreteClassType(elementType, resolvedElementType)) return null
        return collectionType.takeIf { isConcreteClassType(it) }
    }

    private fun assignedReferenceType(
        sageTarget: PyTargetExpression,
        reference: PyReferenceExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyType? {
        val nativeType = context.getType(reference)
        val targets = reference.reference.multiResolve(false)
            .mapNotNull { it.element as? PyTargetExpression }
            .distinct()
        if (targets.size != 1) return nativeType
        val assignmentTarget = targets.single()
        if (assignmentTarget.annotationValue != null) return nativeType
        forLoopElementType(assignmentTarget, context, depth + 1)?.let { return it }
        val assigned = assignmentTarget.findAssignedValue()?.takeIf { it.isValid } ?: return nativeType
        return sourceExpressionType(sageTarget, assigned, context, depth + 1) ?: nativeType
    }

    private fun binaryOperatorType(
        sageTarget: PyTargetExpression,
        expression: PyBinaryExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyType? {
        val operatorText = expression.psiOperator?.text ?: return null
        val methodNames = binaryMethods(operatorText, expression) ?: return null
        val left = expression.leftExpression ?: return null
        val right = expression.rightExpression ?: return null
        sageLiteralReflectedOperatorResult(sageTarget, left, right, methodNames.second, context, depth)
            ?.let { return it }
        val leftType = sourceExpressionType(sageTarget, left, context, depth + 1) as? PyClassType ?: return null
        val leftResult = operatorReturnType(leftType, methodNames.first, context)
        if (leftResult is PyClassType) {
            return leftResult
        }
        if ((leftResult == null || leftResult is PyAnyType) &&
            isPositivePowerWithClosedMultiplication(sageTarget, operatorText, leftType, right, context)
        ) return leftType

        val rightType = sourceExpressionType(sageTarget, right, context, depth + 1) as? PyClassType ?: return null
        val reflectedName = methodNames.second ?: return null
        return operatorReturnType(rightType, reflectedName, context)?.takeIf { it is PyClassType }
    }

    /** `2 * point` in a .sage file: the reflected operator of the Sage right operand answers. */
    private fun sageLiteralReflectedOperatorResult(
        sageTarget: PyTargetExpression,
        left: com.jetbrains.python.psi.PyExpression,
        right: com.jetbrains.python.psi.PyExpression,
        reflectedName: String?,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
        depth: Int,
    ): PyClassType? {
        if (!SageFileUtils.isSageFile(sageTarget.containingFile) || reflectedName == null ||
            !left.text.matches(Regex("[0-9][0-9_]*"))
        ) return null
        val rightType = sourceExpressionType(sageTarget, right, context, depth + 1) as? PyClassType ?: return null
        if (!isSageSdkClassType(rightType)) return null
        return operatorReturnType(rightType, reflectedName, context) as? PyClassType
    }

    private fun isPositivePowerWithClosedMultiplication(
        sageTarget: PyTargetExpression,
        operatorText: String,
        receiverType: PyClassType,
        exponent: com.jetbrains.python.psi.PyExpression,
        context: com.jetbrains.python.psi.types.TypeEvalContext,
    ): Boolean {
        val isPower = operatorText == "**" || (operatorText == "^" && SageFileUtils.isSageFile(sageTarget.containingFile))
        if (!isPower || !isSageSdkClassType(receiverType)) return false
        val digits = exponent.text
        if (!digits.matches(Regex("[0-9][0-9_]*"))) return false
        val positiveExponent = runCatching {
            java.math.BigInteger(digits.replace("_", "")) > java.math.BigInteger.ZERO
        }.getOrDefault(false)
        if (!positiveExponent) return false

        val powerMethod = receiverType.pyClass.findMethodByName("__pow__", true, context) ?: return false
        val powerReturn = (context.getType(powerMethod) as? PyCallableType)?.getReturnType(context)
        if (powerReturn != null && powerReturn !is PyAnyType) return false

        val multiplicationReturn = operatorReturnType(receiverType, "__mul__", context) as? PyClassType ?: return false
        return sameConcreteClassType(receiverType, multiplicationReturn)
    }

    private fun sageSourceImplementation(declaration: PyFunction): PyFunction? {
        val declarationFile = declaration.containingFile.takeIf { it.isValid } ?: return null
        return when {
            SageStubIndex.isSageStubFile(declarationFile) -> SageStubIndex.findSourceImplementation(declaration)
            SageStubIndex.isSageSdkFile(declarationFile) && declarationFile.name.endsWith(".py") -> declaration
            else -> null
        }
    }

    private fun isSageSdkClassType(type: PyClassType): Boolean =
        isConcreteClassType(type) && SageStubIndex.isSageSdkFile(type.pyClass.containingFile)

    private fun operatorReturnType(receiver: PyClassType, methodName: String, context: com.jetbrains.python.psi.types.TypeEvalContext): PyType? {
        val method = receiver.pyClass.findMethodByName(methodName, true, context) ?: return null
        return (context.getType(method) as? PyCallableType)?.getReturnType(context)
    }

    private fun binaryMethods(operator: String, expression: PyBinaryExpression): Pair<String, String?>? = when (operator) {
        "+" -> "__add__" to "__radd__"
        "-" -> "__sub__" to "__rsub__"
        "*" -> "__mul__" to "__rmul__"
        "/" -> "__truediv__" to "__rtruediv__"
        "//" -> "__floordiv__" to "__rfloordiv__"
        "%" -> "__mod__" to "__rmod__"
        "**" -> "__pow__" to "__rpow__"
        "^" -> if (SageFileUtils.isSageFile(expression.containingFile)) "__pow__" to "__rpow__" else "__xor__" to "__rxor__"
        "&" -> "__and__" to "__rand__"
        "|" -> "__or__" to "__ror__"
        "<<" -> "__lshift__" to "__rlshift__"
        ">>" -> "__rshift__" to "__rrshift__"
        else -> null
    }

    private fun sameConcreteClassType(left: PyClassType, right: PyClassType): Boolean =
        isConcreteClassType(left) && isConcreteClassType(right) &&
            left.pyClass == right.pyClass && left.typeArguments == right.typeArguments

    private fun isConcreteClassType(type: PyClassType, depth: Int = 0): Boolean =
        depth <= MAX_SOURCE_TYPE_DEPTH && type.pyClass.isValid && type.typeArguments.all { argument ->
            val argumentClass = argument as? PyClassType ?: return@all false
            isConcreteClassType(argumentClass, depth + 1)
        }

    private fun sameConcreteReturnType(types: List<PyType>): PyClassType? {
        val classes = types.map { it as? PyClassType ?: return null }
        val first = classes.firstOrNull() ?: return null
        return first.takeIf { classes.all { candidate -> sameConcreteClassType(first, candidate) } }
    }

    /** A bounded proof for simple return suites; unsupported control flow stays unknown. */
    private fun returnsValueOnEveryPath(statements: Array<PyStatement>, depth: Int = 0): Boolean {
        ProgressManager.checkCanceled()
        if (depth > MAX_SOURCE_TYPE_DEPTH) return false
        return when (val last = statements.lastOrNull()) {
            is PyReturnStatement -> last.expression != null
            is com.jetbrains.python.psi.PyIfStatement -> {
                val elsePart = last.elsePart ?: return false
                returnsValueOnEveryPath(last.ifPart.statementList.statements, depth + 1) &&
                    last.elifParts.all { returnsValueOnEveryPath(it.statementList.statements, depth + 1) } &&
                    returnsValueOnEveryPath(elsePart.statementList.statements, depth + 1)
            }
            else -> false
        }
    }

    private const val MAX_SOURCE_TYPE_DEPTH = 16
}
