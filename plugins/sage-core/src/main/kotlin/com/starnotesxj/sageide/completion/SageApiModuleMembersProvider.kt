package com.starnotesxj.sageide.completion

import com.intellij.psi.PsiElement
import com.intellij.util.Function
import com.jetbrains.python.codeInsight.PyCustomMember
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.types.PyType
import com.jetbrains.python.psi.resolve.PointInImport
import com.jetbrains.python.psi.resolve.PyResolveContext
import com.jetbrains.python.psi.PyPsiFacade
import com.jetbrains.python.psi.types.PyModuleMembersProvider
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sageide.type.SageTypeLowering

/**
 * Supplies direct exports from the validated Sage index to imported Sage modules.
 *
 * This is intentionally separate from the .sage implicit sage.all contributor:
 * ordinary Python receives only members of a module it explicitly imports, while
 * native .py/.pyi PSI remains authoritative and wins duplicate names.
 */
class SageApiModuleMembersProvider : PyModuleMembersProvider() {
    override fun getMembers(module: PyFile, point: PointInImport, context: TypeEvalContext): Collection<PyCustomMember> {
        // Active Sage SDK source/stubs are native PSI and must remain
        // authoritative. Feeding indexed synthetic declarations into their own
        // module resolution (including runtime .py packages, not just .pyi)
        // creates parentless custom PSI elements, which PythonCore can revisit
        // indefinitely during inspections.
        if (SageFileUtils.isSageFile(module) || SageStubIndex.isSageSdkFile(module)) return emptyList()
        val qualifiedName = moduleQName(module) ?: return emptyList()
        return indexedMembers(module, qualifiedName)
    }

    override fun resolveMember(module: PyFile, name: String, resolveContext: PyResolveContext): PsiElement? {
        if (SageFileUtils.isSageFile(module) || SageStubIndex.isSageSdkFile(module)) return null
        val qualifiedName = moduleQName(module) ?: return null
        return indexedMembers(module, qualifiedName)
            .firstOrNull { it.name == name }
            ?.resolve(module, resolveContext)
    }

    override fun getMembersByQName(module: PyFile, qName: String, context: TypeEvalContext): Collection<PyCustomMember> =
        if (!SageFileUtils.isSageFile(module) && !SageStubIndex.isSageSdkFile(module) && qName.startsWith("sage.")) {
            indexedMembers(module, qName)
        } else {
            emptyList()
        }

    private fun moduleQName(module: PyFile): String? =
        module.virtualFile?.let { virtualFile ->
            PyPsiFacade.getInstance(module.project).findShortestImportableName(virtualFile, module)
        }

    private fun indexedMembers(module: PyFile, moduleQName: String): Collection<PyCustomMember> {
        if (!moduleQName.startsWith("sage.")) return emptyList()
        val facade = SageApiIntelligenceFacade.getInstance()
        return facade.moduleEntries(moduleQName)
            .asSequence()
            .filter { it.kind != SageApiSymbolKind.MODULE }
            .map { entry -> entry.toCustomMember(module) }
            .distinctBy { it.name }
            .toList()
    }

    private fun SageApiEntry.toCustomMember(module: PyFile): PyCustomMember {
        val name = qualifiedName.substringAfterLast('.')
        val facade = SageApiIntelligenceFacade.getInstance()
        val query = facade.query()

        fun typedValue(entry: SageApiEntry): PyCustomMember = PyCustomMember(
            name,
            null,
            Function<PsiElement, PyType?> { location ->
                val valueType = entry.valueType ?: return@Function null
                val activeQuery = SageApiIntelligenceFacade.getInstance().query() ?: return@Function null
                SageTypeLowering.lower(
                    valueType,
                    location,
                    TypeEvalContext.codeAnalysis(location.project, location.containingFile),
                    activeQuery,
                )
            },
        ).toPsiElement(module)

        fun typedCallable(entry: SageApiEntry): PyCustomMember = PyCustomMember(
            name,
            null,
            Function<PsiElement, PyType?> { location ->
                val activeQuery = SageApiIntelligenceFacade.getInstance().query() ?: return@Function null
                SageTypeLowering.lowerSignatures(
                    activeQuery.signatures(entry.qualifiedName),
                    location,
                    TypeEvalContext.codeAnalysis(location.project, location.containingFile),
                    activeQuery,
                )
            },
        ).toPsiElement(module).asFunction()

        return when (kind) {
            SageApiSymbolKind.FUNCTION -> typedCallable(this)
            SageApiSymbolKind.PROPERTY,
            SageApiSymbolKind.CONSTANT -> typedValue(this)
            SageApiSymbolKind.CLASS -> PyCustomMember(name, null, false)
                .resolvesToClass(qualifiedName)
                .asFunction()
            SageApiSymbolKind.ALIAS -> {
                val targetEntry = aliases.asSequence()
                    .mapNotNull { facade.resolve(it) }
                    .distinctBy { it.qualifiedName to it.kind }
                    .singleOrNull()
                when (targetEntry?.kind) {
                    SageApiSymbolKind.FUNCTION -> typedCallable(targetEntry)
                    SageApiSymbolKind.PROPERTY,
                    SageApiSymbolKind.CONSTANT -> typedValue(targetEntry)
                    SageApiSymbolKind.CLASS -> PyCustomMember(name, null, false)
                        .resolvesToClass(targetEntry.qualifiedName)
                        .asFunction()
                    else -> PyCustomMember(name, null, false).toPsiElement(module)
                }
            }
            else -> PyCustomMember(name, null, false).toPsiElement(module)
        }
    }
}
