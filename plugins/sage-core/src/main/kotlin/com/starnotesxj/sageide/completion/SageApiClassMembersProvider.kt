package com.starnotesxj.sageide.completion

import com.intellij.psi.PsiElement
import com.jetbrains.python.codeInsight.PyCustomMember
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.resolve.PyResolveContext
import com.jetbrains.python.psi.types.PyClassMembersProviderBase
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sageide.sugar.SageFileUtils

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
        val owner = clazz.pyClass.qualifiedName ?: return emptyList()
        return query.members(owner)
            .asSequence()
            .map { entry ->
                val memberName = entry.qualifiedName.substringAfterLast('.')
                indexedMember(memberName, owner, entry.kind)
            }
            .distinctBy { it.name }
            .toList()
    }

    override fun resolveMember(type: PyClassType, name: String, location: PsiElement?, resolveContext: PyResolveContext): PsiElement? {
        val query = SageApiIndexService.getInstance().query() ?: return null
        if (!isSageContext(location, type.pyClass)) return null
        val owner = type.pyClass.qualifiedName ?: return null
        return query.members(owner, name).firstOrNull()?.let {
            // The custom-member path supplies a synthetic typed target for completion;
            // name resolution remains additive and never fabricates a method-specific rule.
            indexedMember(name, owner, it.kind).resolve(type.pyClass, resolveContext)
        }
    }

    private fun indexedMember(name: String, owner: String, kind: SageApiSymbolKind): PyCustomMember =
        PyCustomMember(name, owner, false).apply {
            if (kind == SageApiSymbolKind.METHOD) asFunction()
        }

    private fun isSageContext(location: PsiElement?, owner: PyClass): Boolean =
        SageFileUtils.isSageFile(location?.containingFile) || owner.qualifiedName?.startsWith("sage.") == true
}

