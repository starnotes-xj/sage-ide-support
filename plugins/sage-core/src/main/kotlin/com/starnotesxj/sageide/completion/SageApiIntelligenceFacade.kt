package com.starnotesxj.sageide.completion

import com.starnotesxj.sagemath.sageapi.*

/**
 * Read-only plugin boundary for all indexed Sage intelligence.
 *
 * Providers should depend on this facade rather than obtaining the application
 * service and applying their own query conventions.  The facade deliberately
 * keeps the index optional: a missing or rejected index must produce no Sage
 * result instead of an invented type or completion item.  Native Python PSI
 * and .pyi declarations remain authoritative; these calls expose only the
 * versioned index's additive facts.
 */
class SageApiIntelligenceFacade(private val service: SageApiIndexService) {
    /** The currently installed immutable query, or null when unavailable. */
    fun query(): SageApiIndexQuery? = service.query()

    /** The currently installed index, or null when unavailable. */
    fun index(): SageApiIndex? = query()?.index

    fun resolve(name: String, kind: SageApiSymbolKind? = null): SageApiEntry? =
        query()?.resolve(name, kind)

    fun find(name: String, kind: SageApiSymbolKind? = null): SageApiEntry? =
        query()?.find(name, kind)

    fun moduleEntries(moduleQualifiedName: String): List<SageApiEntry> =
        query()?.moduleEntries(moduleQualifiedName).orEmpty()

    fun members(ownerQualifiedName: String): List<SageApiEntry> =
        query()?.members(ownerQualifiedName).orEmpty()

    fun members(ownerQualifiedName: String, memberName: String): List<SageApiEntry> =
        query()?.members(ownerQualifiedName, memberName).orEmpty()

    fun signatures(functionQualifiedName: String): List<SageApiSignature> =
        query()?.signatures(functionQualifiedName).orEmpty()

    fun documentation(name: String): SageApiDocumentation? =
        query()?.resolve(name)?.let { SageApiDocumentationService.getInstance().documentation(it) }

    companion object {
        /** Resolve the shared facade from the current IDE application. */
        @JvmStatic
        fun getInstance(): SageApiIntelligenceFacade =
            SageApiIntelligenceFacade(SageApiIndexService.getInstance())
    }
}
