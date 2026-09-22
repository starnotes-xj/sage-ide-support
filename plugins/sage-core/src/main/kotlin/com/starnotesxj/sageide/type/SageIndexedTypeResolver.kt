package com.starnotesxj.sageide.type

import com.intellij.psi.PsiElement
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyBinaryExpression
import com.jetbrains.python.psi.PyExpression
import com.jetbrains.python.psi.PyNumericLiteralExpression
import com.jetbrains.python.psi.PyParenthesizedExpression
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyTargetExpression
import com.starnotesxj.sageide.completion.SageApiIndexService
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageTypeExpression
import com.starnotesxj.sagemath.sageapi.SageTypeRefExpressionParser

/**
 * Resolves concrete Sage owners directly from the immutable API contract.
 *
 * A remote WSL interpreter may have a valid Sage installation while PyCharm's
 * skeleton generator has not copied every `.pyi` class into the local PSI
 * index.  The normal Python type engine quite correctly refuses to fabricate
 * a `PyClassType` in that situation, but completion still has an exact source
 * of truth: the indexed return expression and the receiver's `__call__`
 * contract.  This resolver follows those expressions through assignments and
 * nested calls and returns canonical class names only.  It deliberately does
 * not return `Parent`, `Element`, `Any`, or an arbitrary short-name match.
 */
object SageIndexedTypeResolver {
    fun ownersForTarget(target: PyTargetExpression, query: SageApiIndexQuery? = currentQuery()): Set<String> {
        val index = query ?: return emptySet()
        return Resolver(index).ownersForTarget(target)
    }

    fun ownersForExpression(expression: PyExpression, query: SageApiIndexQuery? = currentQuery()): Set<String> {
        val index = query ?: return emptySet()
        return Resolver(index).ownersForExpression(expression)
    }

    private fun currentQuery(): SageApiIndexQuery? = SageApiIndexService.getInstance().query()

    private class Resolver(private val query: SageApiIndexQuery) {
        private val expressionStack = HashSet<PsiElement>()
        private val targetStack = HashSet<PyTargetExpression>()

        fun ownersForTarget(target: PyTargetExpression): Set<String> {
            if (!targetStack.add(target)) return emptySet()
            return try {
                val assigned = target.findAssignedValue() as? PyExpression ?: return emptySet()
                ownersForExpression(assigned)
            } finally {
                targetStack.remove(target)
            }
        }

        fun ownersForExpression(expression: PyExpression): Set<String> {
            if (!expressionStack.add(expression)) return emptySet()
            return try {
                when (expression) {
                    is PyNumericLiteralExpression -> numericOwners(expression)
                    is PyParenthesizedExpression -> expression.containedExpression?.let(::ownersForExpression).orEmpty()
                    is PyBinaryExpression -> ownersForBinary(expression)
                    is PyCallExpression -> ownersForCall(expression)
                    is PyReferenceExpression -> ownersForReference(expression)
                    else -> emptySet()
                }
            } finally {
                expressionStack.remove(expression)
            }
        }

        private fun ownersForReference(reference: PyReferenceExpression): Set<String> {
            val target = reference.reference?.resolve() as? PyTargetExpression
            if (target != null) return ownersForTarget(target)
            if (reference.qualifier != null) return ownersForQualifiedMember(reference)

            val name = reference.referencedName ?: return emptySet()
            val namespaceEntry = query.namespaceEntry("sage.all", name)
            return namespaceEntry?.let(::ownersForValueEntry).orEmpty()
        }

        private fun ownersForCall(call: PyCallExpression): Set<String> {
            val callee = call.callee as? PyReferenceExpression ?: return emptySet()
            if (callee.qualifier != null) return ownersForQualifiedMember(callee)

            // A target such as `F = GF(11)` is a callable parent object.  Its
            // concrete element is described by the parent's `__call__` entry.
            val target = callee.reference?.resolve() as? PyTargetExpression
            if (target != null) {
                return ownersForCallableParents(ownersForTarget(target))
            }

            val name = callee.referencedName ?: return emptySet()
            val entry = query.namespaceEntry("sage.all", name)
                ?: query.resolve(name)
                ?: return emptySet()
            return ownersForCallableEntry(entry)
        }

        /**
         * Resolve an operator expression from its concrete Sage protocols.
         *
         * A generic scalar slot such as ``Integer.__mul__(other: DYNAMIC) ->
         * Integer`` is not proof that it handles an arbitrary Sage element:
         * Python may instead dispatch to the right operand's reflected slot.
         * We therefore use a direct contract only when its parameters are
         * fully statically described, then fall through to the reflected and
         * Cython-private spelling when needed.  ``Self`` is bound to the
         * proven right-hand concrete owner, never to a common base class.
         */
        private fun ownersForBinary(expression: PyBinaryExpression): Set<String> {
            val operator = expression.referencedName ?: return emptySet()
            val left = expression.leftExpression ?: return emptySet()
            val right = expression.rightExpression ?: return emptySet()
            val leftOwners = ownersForExpression(left)
            val rightOwners = ownersForExpression(right)

            operatorResultOwners(leftOwners, operator).takeIf { it.isNotEmpty() }?.let { return it }

            val reflected = reflectedOperator(operator) ?: return emptySet()
            operatorResultOwners(rightOwners, reflected).takeIf { it.isNotEmpty() }?.let { return it }
            cythonReflectedOperatorImplementation(reflected)?.let { cythonName ->
                operatorResultOwners(rightOwners, cythonName).takeIf { it.isNotEmpty() }?.let { return it }
            }
            return emptySet()
        }

        private fun operatorResultOwners(owners: Set<String>, memberName: String): Set<String> =
            owners.flatMapTo(linkedSetOf()) { owner ->
                val members = query.members(owner, memberName)
                    .filter { it.kind == com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.METHOD && it.signatures.isNotEmpty() }
                val owned = members.filter { it.qualifiedName.substringBeforeLast('.') == owner }
                val candidate = (owned.ifEmpty { members }).singleOrNull() ?: return@flatMapTo emptySet()
                candidate.signatures
                    .asSequence()
                    .filter(::hasFullyKnownOperatorParameters)
                    .flatMap { signature -> concreteOwners(signature, owner).asSequence() }
                    .toCollection(linkedSetOf())
            }

        private fun hasFullyKnownOperatorParameters(signature: SageApiSignature): Boolean =
            signature.parameters.all { it.type.state.name == "KNOWN" }

        private fun reflectedOperator(operator: String): String? = when (operator) {
            "__add__" -> "__radd__"
            "__sub__" -> "__rsub__"
            "__mul__" -> "__rmul__"
            "__matmul__" -> "__rmatmul__"
            "__truediv__" -> "__rtruediv__"
            "__floordiv__" -> "__rfloordiv__"
            "__mod__" -> "__rmod__"
            "__pow__" -> "__rpow__"
            else -> null
        }

        private fun cythonReflectedOperatorImplementation(operator: String): String? {
            if (!operator.startsWith("__r") || !operator.endsWith("__")) return null
            val slot = operator.removePrefix("__").removeSuffix("__")
            return slot.takeIf { it.length > 1 }?.let { "_${it}_" }
        }

        private fun ownersForQualifiedMember(reference: PyReferenceExpression): Set<String> {
            val qualifier = reference.qualifier ?: return emptySet()
            val memberName = reference.referencedName ?: return emptySet()
            return ownersForExpression(qualifier)
                .flatMapTo(linkedSetOf()) { owner ->
                    query.members(owner, memberName)
                        .asSequence()
                        .flatMap { entry -> entry.signatures.asSequence() }
                        .flatMapTo(linkedSetOf(), ::concreteOwners)
                }
        }

        private fun ownersForCallableParents(parents: Set<String>): Set<String> =
            parents.flatMapTo(linkedSetOf()) { owner ->
                query.members(owner, "__call__")
                    .asSequence()
                    .flatMap { entry -> entry.signatures.asSequence() }
                    .flatMapTo(linkedSetOf(), ::concreteOwners)
            }

        private fun ownersForCallableEntry(entry: com.starnotesxj.sagemath.sageapi.SageApiEntry): Set<String> =
            entry.signatures
                .asSequence()
                .flatMapTo(linkedSetOf(), ::concreteOwners)
                .ifEmpty {
                    // Sage exposes ring/field/parent singletons such as ZZ,
                    // QQ and RR as constants.  Their valueType is the exact
                    // parent class from the stub, whose __call__ contract is
                    // the only authoritative result for `ZZ(value)`.
                    // This is data-driven for every typed callable constant;
                    // an ordinary constant without a proven __call__ simply
                    // remains unresolved.
                    ownersForCallableParents(ownersForValueEntry(entry))
                }

        private fun ownersForValueEntry(entry: com.starnotesxj.sagemath.sageapi.SageApiEntry): Set<String> =
            entry.valueType?.let(::concreteOwners).orEmpty()

        private fun concreteOwners(signature: SageApiSignature, selfOwner: String? = null): Set<String> {
            val returnType = signature.returnType
            if (returnType.state.name != "KNOWN" || returnType.expression.isNullOrBlank()) return emptySet()
            val expression = SageTypeRefExpressionParser.parse(
                returnType.expression!!,
                signature.typeParameters.map { it.name }.toSet(),
                signature.typeParameters.filter { it.kind.name == "PARAM_SPEC" }.map { it.name }.toSet(),
            ) ?: return emptySet()
            return concreteOwners(expression, selfOwner)
        }

        private fun concreteOwners(
            returnType: com.starnotesxj.sagemath.sageapi.SageTypeRef,
            selfOwner: String? = null,
        ): Set<String> {
            if (returnType.state.name != "KNOWN" || returnType.expression.isNullOrBlank()) return emptySet()
            val expression = SageTypeRefExpressionParser.parse(
                returnType.expression!!,
                emptySet(),
                emptySet(),
            ) ?: return emptySet()
            return concreteOwners(expression, selfOwner)
        }

        private fun concreteOwners(expression: SageTypeExpression, selfOwner: String? = null): Set<String> = when (expression) {
            is SageTypeExpression.TypeVariable ->
                selfOwner.takeIf { expression.name == "Self" || expression.name == "typing.Self" }?.let(::setOf).orEmpty()
            is SageTypeExpression.Name -> canonicalClass(expression.qualifiedName)
            is SageTypeExpression.Generic -> canonicalClass(expression.base.qualifiedName)
            is SageTypeExpression.Union -> expression.members.flatMapTo(linkedSetOf()) { concreteOwners(it, selfOwner) }
            is SageTypeExpression.Optional -> concreteOwners(expression.element, selfOwner)
            is SageTypeExpression.Callable -> emptySet()
            is SageTypeExpression.ParamSpecAccess,
            SageTypeExpression.NoneType,
            SageTypeExpression.EllipsisType,
            is SageTypeExpression.Literal -> emptySet()
        }

        private fun canonicalClass(rawName: String): Set<String> {
            val canonical = query.resolveKnownClassName(rawName)
                ?: rawName.takeIf { it.startsWith("sage.") && query.findAll(it, com.starnotesxj.sagemath.sageapi.SageApiSymbolKind.CLASS).size == 1 }
                ?: return emptySet()
            return setOf(canonical)
        }

        private fun numericOwners(expression: PyNumericLiteralExpression): Set<String> {
            val name = if (expression.isIntegerLiteral) {
                "sage.rings.integer.Integer"
            } else {
                "sage.rings.real_mpfr.RealNumber"
            }
            return canonicalClass(name)
        }
    }
}
