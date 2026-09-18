package com.starnotesxj.sageide.completion

import com.starnotesxj.sagemath.sageapi.SageApiConfidence
import com.starnotesxj.sagemath.sageapi.SageApiDocumentation
import com.starnotesxj.sagemath.sageapi.SageApiDynamicity
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndex
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageApiSourceRef
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeRef

/** Immutable metadata exposed to PSI providers without exposing service state. */
data class SageApiTypeMetadata(
    val type: SageTypeRef?,
    val dynamicity: SageApiDynamicity,
    val confidence: SageApiConfidence,
    val sources: List<SageApiSourceRef>,
)

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

    /** Service load metadata for headless probes and diagnostics. */
    fun loadState(): SageApiIndexLoadState = service.loadState()

    fun resolve(name: String, kind: SageApiSymbolKind? = null): SageApiEntry? =
        query()?.resolve(name, kind)

    fun find(name: String, kind: SageApiSymbolKind? = null): SageApiEntry? =
        query()?.find(name, kind)

    /** Metadata for a symbol, preserving explicit UNKNOWN/DYNAMIC states. */
    fun typeMetadata(name: String, kind: SageApiSymbolKind? = null): SageApiTypeMetadata? =
        resolve(name, kind)?.let { entry ->
            SageApiTypeMetadata(
                type = entry.valueType,
                dynamicity = entry.dynamicity,
                confidence = entry.confidence,
                sources = entry.sources,
            )
        }

    fun entriesOwnedBy(ownerQualifiedName: String): List<SageApiEntry> =
        query()?.entriesOwnedBy(ownerQualifiedName).orEmpty()

    fun moduleEntries(moduleQualifiedName: String): List<SageApiEntry> =
        query()?.moduleEntries(moduleQualifiedName).orEmpty()

    /** Resolve a direct module export without falling back to global short-name collisions. */
    fun moduleEntry(moduleQualifiedName: String, shortName: String): SageApiEntry? =
        query()?.moduleEntries(moduleQualifiedName)
            ?.filter { it.qualifiedName.substringAfterLast('.') == shortName }
            ?.distinctBy { it.qualifiedName to it.kind }
            ?.singleOrNull()

    /** Root namespace exports; defaults to the runtime-injected sage.all module. */
    fun rootEntries(rootQualifiedName: String = "sage.all"): List<SageApiEntry> =
        query()?.namespaceEntries(rootQualifiedName).orEmpty()

    fun rootEntry(shortName: String, rootQualifiedName: String = "sage.all"): SageApiEntry? =
        query()?.namespaceEntry(rootQualifiedName, shortName)

    fun members(ownerQualifiedName: String): List<SageApiEntry> =
        query()?.members(ownerQualifiedName).orEmpty()

    fun members(ownerQualifiedName: String, memberName: String): List<SageApiEntry> =
        query()?.members(ownerQualifiedName, memberName).orEmpty()

    fun callReturnTypes(functionQualifiedName: String): List<SageTypeRef> =
        query()?.callReturnTypes(functionQualifiedName).orEmpty()

    fun signatures(functionQualifiedName: String): List<SageApiSignature> =
        query()?.signatures(functionQualifiedName).orEmpty()

    fun documentation(name: String): SageApiDocumentation? =
        query()?.resolve(name)?.let { SageApiDocumentationService.getInstance().documentation(it) }

    fun uniqueKnownReturnType(functionQualifiedName: String): SageTypeRef? =
        query()?.uniqueKnownReturnType(functionQualifiedName)

    fun uniqueKnownReturnExpression(functionQualifiedName: String): SageTypeRef? =
        query()?.uniqueKnownReturnExpression(functionQualifiedName)

    fun resolveKnownClassName(typeExpression: String): String? =
        query()?.resolveKnownClassName(typeExpression)

    fun reachableTypeNames(observedName: String): Set<String> =
        query()?.reachableTypeNames(observedName).orEmpty()

    fun isKnownClassName(name: String): Boolean =
        query()?.isKnownClassName(name) == true

    companion object {
        /** Resolve the shared facade from the current IDE application. */
        @JvmStatic
        fun getInstance(): SageApiIntelligenceFacade =
            SageApiIntelligenceFacade(SageApiIndexService.getInstance())
    }
}
