package com.starnotesxj.sageide.type

import com.intellij.psi.PsiElement
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyExpression
import com.jetbrains.python.psi.PyNumericLiteralExpression
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
            return namespaceEntry?.let(::ownersForCallableEntry).orEmpty()
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

        private fun concreteOwners(signature: SageApiSignature): Set<String> {
            val returnType = signature.returnType
            if (returnType.state.name != "KNOWN" || returnType.expression.isNullOrBlank()) return emptySet()
            val expression = SageTypeRefExpressionParser.parse(
                returnType.expression!!,
                signature.typeParameters.map { it.name }.toSet(),
                signature.typeParameters.filter { it.kind.name == "PARAM_SPEC" }.map { it.name }.toSet(),
            ) ?: return emptySet()
            return concreteOwners(expression)
        }

        private fun concreteOwners(expression: SageTypeExpression): Set<String> = when (expression) {
            is SageTypeExpression.Name -> canonicalClass(expression.qualifiedName)
            is SageTypeExpression.Generic -> canonicalClass(expression.base.qualifiedName)
            is SageTypeExpression.Union -> expression.members.flatMapTo(linkedSetOf(), ::concreteOwners)
            is SageTypeExpression.Optional -> concreteOwners(expression.element)
            is SageTypeExpression.Callable -> emptySet()
            is SageTypeExpression.TypeVariable,
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
