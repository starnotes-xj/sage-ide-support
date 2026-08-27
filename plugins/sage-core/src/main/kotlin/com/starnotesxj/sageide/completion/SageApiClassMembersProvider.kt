package com.starnotesxj.sageide.completion

import com.intellij.psi.PsiElement
import com.jetbrains.python.codeInsight.PyCustomMember
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.resolve.PyResolveContext
import com.jetbrains.python.psi.types.PyClassMembersProviderBase
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyType
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.intellij.util.Function
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sageide.type.SageTypeLowering

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
            // Query metadata preserves same-owner METHOD/PROPERTY/CONSTANT
            // declarations for completeness. Completion still exposes one
            // effective Python attribute, preferring a callable view when the
            // generated stub contains both a method and property declaration.
            .groupBy { it.name }
            .values
            .map { variants ->
                variants.sortedWith(compareByDescending<PyCustomMember> { it.isFunction }.thenBy { it.name }).first()
            }
            .sortedBy { it.name }
            .toList()
    }

    override fun resolveMember(type: PyClassType, name: String, location: PsiElement?, resolveContext: PyResolveContext): PsiElement? {
        val query = SageApiIndexService.getInstance().query() ?: return null
        if (!isSageContext(location, type.pyClass)) return null
        val owner = SageStubIndex.canonicalQualifiedName(type.pyClass) ?: return null
        val entry = query.members(owner, name).firstOrNull() ?: return null
        // Prefer the native PSI declaration when one exists.  PythonCore keeps
        // that element attached to its stub file; forcing a synthetic custom
        // element here can create a parent-less `MyInstanceElement`, which
        // breaks subsequent documentation/reference resolution.  The indexed
        // member remains available for completion and is used only when native
        // PSI has no declaration.
        val native = type.pyClass.findMethodByName(name, true, TypeEvalContext.codeAnalysis(
            location?.project ?: type.pyClass.project,
            location?.containingFile,
        ))
        if (native != null) return native
        return indexedMember(name, owner, entry).resolve(location ?: type.pyClass, resolveContext)
    }

    private fun indexedMember(name: String, owner: String, entry: SageApiEntry): PyCustomMember = when (entry.kind) {
        SageApiSymbolKind.METHOD -> PyCustomMember(
            name,
            owner,
            Function<PsiElement, PyType?> { location -> indexedCallableType(location, entry) },
        ).asFunction()
        SageApiSymbolKind.PROPERTY,
        SageApiSymbolKind.CONSTANT -> PyCustomMember(
            name,
            owner,
            Function<PsiElement, PyType?> { location -> indexedValueType(location, entry) },
        )
        else -> PyCustomMember(name, owner, false)
    }

    /** Lower every agreed indexed signature without discarding return structure. */
    private fun indexedCallableType(location: PsiElement, entry: SageApiEntry): PyType? {
        val query = SageApiIndexService.getInstance().query() ?: return null
        return SageTypeLowering.lowerSignatures(query.signatures(entry.qualifiedName), location, TypeEvalContext.codeAnalysis(location.project, location.containingFile), query)
    }

    private fun indexedValueType(location: PsiElement, entry: SageApiEntry): PyType? {
        val query = SageApiIndexService.getInstance().query() ?: return null
        val valueType = entry.valueType ?: return null
        return SageTypeLowering.lower(
            valueType,
            location,
            TypeEvalContext.codeAnalysis(location.project, location.containingFile),
            query,
        )
    }

    private fun isSageContext(location: PsiElement?, owner: PyClass): Boolean =
        SageFileUtils.isSageFile(location?.containingFile) ||
            SageStubIndex.canonicalQualifiedName(owner)?.startsWith("sage.") == true
}
