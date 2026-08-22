package com.starnotesxj.sagemath.sageapi

/**
 * Merges extractor outputs from runtime, stub, signature, and documentation
 * sources into one immutable, version-bound index. The IDE consumer does not
 * contain Sage symbol-specific rules; all symbol facts arrive as data.
 */
class SageApiNormalizer {
    fun normalize(version: SageApiVersion, rawSymbols: List<SageRawSymbol>): SageApiNormalizationResult {
        val diagnostics = mutableListOf<SageApiDiagnostic>()
        val grouped = rawSymbols.groupBy { it.qualifiedName to it.kind }
        val entries = grouped.map { (key, candidates) ->
            val (qualifiedName, kind) = key
            val ordered = candidates.sortedWith(compareBy({ it.source.kind.name }, { it.source.locator }))
            val conflict = conflictingSignatures(ordered)
            if (candidates.size > 1) {
                diagnostics += SageApiDiagnostic(
                    kind = if (conflict) SageApiDiagnosticKind.CONFLICT else SageApiDiagnosticKind.DUPLICATE,
                    qualifiedName = qualifiedName,
                    message = if (conflict) "Conflicting declarations were merged as dynamic" else "Duplicate declarations were merged",
                    sources = ordered.map { it.source },
                )
            }
            val signatures = if (conflict) listOf(SageApiSignature.dynamic()) else ordered.flatMap { it.signatures }.distinct()
            SageApiEntry(
                qualifiedName = qualifiedName,
                kind = kind,
                signatures = signatures,
                valueType = ordered.mapNotNull { it.valueType }.firstOrNull(),
                parents = ordered.flatMap { it.parents }.distinct().sorted(),
                protocols = ordered.flatMap { it.protocols }.distinct().sorted(),
                aliases = ordered.flatMap { it.aliases }.distinct().sorted(),
                documentation = ordered.firstNotNullOfOrNull { it.documentation },
                dynamicity = when {
                    conflict -> SageApiDynamicity.DYNAMIC
                    ordered.any { it.dynamicity == SageApiDynamicity.DYNAMIC } -> SageApiDynamicity.DYNAMIC
                    ordered.any { it.dynamicity == SageApiDynamicity.UNKNOWN } -> SageApiDynamicity.UNKNOWN
                    else -> SageApiDynamicity.STATIC
                },
                confidence = ordered.maxBy { confidenceRank(it.confidence) }.confidence,
                sources = ordered.map { it.source }.distinct(),
            )
        }.sortedWith(compareBy<SageApiEntry> { it.qualifiedName }.thenBy { it.kind.name })

        entries.filter { it.kind == SageApiSymbolKind.ALIAS && it.aliases.isEmpty() }.forEach {
            diagnostics += SageApiDiagnostic(
                SageApiDiagnosticKind.UNRESOLVED_ALIAS,
                it.qualifiedName,
                "Alias has no target",
                it.sources,
            )
        }
        val sourceDigests = entries.flatMap { it.sources }.mapNotNull { source ->
            source.digest?.let { digest -> source.locator to digest }
        }.toMap().toSortedMap()
        return SageApiNormalizationResult(
            index = SageApiIndex(
                sageVersion = version.sage,
                pythonVersion = version.python,
                entries = entries,
                sourceDigests = sourceDigests,
            ),
            diagnostics = diagnostics.sortedWith(compareBy<SageApiDiagnostic> { it.qualifiedName }.thenBy { it.kind.name }),
        )
    }

    private fun conflictingSignatures(symbols: List<SageRawSymbol>): Boolean {
        val signatures = symbols.flatMap { it.signatures }.distinct()
        if (signatures.size < 2) return false
        return signatures.groupBy { it.parameters.map(SageApiParameter::name) }.values.any { group ->
            group.map { it.returnType }.distinct().size > 1
        }
    }

    private fun confidenceRank(value: SageApiConfidence): Int = when (value) {
        SageApiConfidence.HIGH -> 4
        SageApiConfidence.MEDIUM -> 3
        SageApiConfidence.LOW -> 2
        SageApiConfidence.UNKNOWN -> 1
    }
}
