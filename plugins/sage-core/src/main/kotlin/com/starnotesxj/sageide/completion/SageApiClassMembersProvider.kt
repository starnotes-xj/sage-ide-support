package com.starnotesxj.sageide.completion

import com.intellij.psi.PsiElement
import com.jetbrains.python.codeInsight.PyCustomMember
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.resolve.PyResolveContext
import com.jetbrains.python.psi.types.PyCallableParameterImpl
import com.jetbrains.python.psi.types.PyCallableTypeImpl
import com.jetbrains.python.psi.types.PyClassMembersProviderBase
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyClassTypeImpl
import com.jetbrains.python.psi.types.PyType
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.intellij.util.Function
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex

/**
 * Supplies indexed Sage members to the Python type engine.
 *
 * It is additive: native PSI/.pyi members remain authoritative, while this
 * provider fills gaps from the versioned index. It never branches on a Sage
 * method name; all behavior is driven by owner and indexed member kind.
 */
class SageApiClassMembersProvider : PyClassMembersProviderBase() {
    override fun getMembers(clazz: PyClassType, location: PsiElement?, context: TypeEvalContext): Collection<PyCustomMember> {
        val query = SageApiIndexService.getInstance().query() ?: return emptyList()
        if (!isSageContext(location, clazz.pyClass)) return emptyList()
        val owner = SageStubIndex.canonicalQualifiedName(clazz.pyClass) ?: return emptyList()
        return query.members(owner)
            .asSequence()
            .map { entry ->
                val memberName = entry.qualifiedName.substringAfterLast('.')
                indexedMember(memberName, owner, entry)
            }
            .distinctBy { it.name }
            .toList()
    }

    override fun resolveMember(type: PyClassType, name: String, location: PsiElement?, resolveContext: PyResolveContext): PsiElement? {
        val query = SageApiIndexService.getInstance().query() ?: return null
        if (!isSageContext(location, type.pyClass)) return null
        val owner = SageStubIndex.canonicalQualifiedName(type.pyClass) ?: return null
        val entry = query.members(owner, name).firstOrNull() ?: return null
        // The custom-member path supplies a synthetic typed target for completion;
        // name resolution remains additive and never fabricates a method-specific rule.
        return indexedMember(name, owner, entry)
            .alwaysResolveToCustomElement()
            .resolve(location ?: type.pyClass, resolveContext)
    }

    private fun indexedMember(name: String, owner: String, entry: SageApiEntry): PyCustomMember {
        if (entry.kind != SageApiSymbolKind.METHOD) return PyCustomMember(name, owner, false)

        return PyCustomMember(
            name,
            owner,
            Function<PsiElement, PyType?> { location ->
                indexedCallableType(location, entry)
            },
        ).asFunction()
    }

    /**
     * Translate only a unique indexed class return into a real Python callable
     * type.  Unknown, dynamic, union, generic, and PSI-unresolvable returns
     * deliberately stay untyped rather than inventing a member-call result.
     */
    private fun indexedCallableType(location: PsiElement, entry: SageApiEntry): PyType? {
        val query = SageApiIndexService.getInstance().query() ?: return null
        val returnExpression = query.uniqueKnownReturnType(entry.qualifiedName)?.expression ?: return null
        val className = query.resolveKnownClassName(returnExpression) ?: return null
        val returnType = PyClassTypeImpl.createTypeByQName(location, className, false) ?: return null
        val signatures = query.signatures(entry.qualifiedName)
        val parameterNames = signatures
            .takeIf { it.isNotEmpty() && it.map { signature -> signature.parameters.map { it.name } }.distinct().size == 1 }
            ?.first()
            ?.parameters
            ?.map { parameter -> PyCallableParameterImpl.nonPsi(parameter.name, null) }
            .orEmpty()
        return PyCallableTypeImpl(parameterNames, returnType)
    }

    private fun isSageContext(location: PsiElement?, owner: PyClass): Boolean =
        SageFileUtils.isSageFile(location?.containingFile) ||
            SageStubIndex.canonicalQualifiedName(owner)?.startsWith("sage.") == true
}

