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
        return signatures.withIndex().any { (index, signature) ->
            signatures.drop(index + 1).any { other -> !canCoexistAsOverloads(signature, other) }
        }
    }

    /**
     * Keeps an overload only when its call shape is provably disjoint from the
     * other signature. Unknown types, optional/variadic shapes, and ambiguous
     * arity remain Dynamic rather than being guessed into an overload set.
     */
    private fun canCoexistAsOverloads(left: SageApiSignature, right: SageApiSignature): Boolean {
        if (left.returnType.state != SageTypeState.KNOWN || right.returnType.state != SageTypeState.KNOWN) {
            return false
        }
        if (left.parameters.size != right.parameters.size) return false
        if (left.parameters.any { it.type.state != SageTypeState.KNOWN } || right.parameters.any { it.type.state != SageTypeState.KNOWN }) {
            return false
        }
        if (containsLiteralAndWideType(left, right)) return false
        if (sameParameterShape(left, right)) return left.returnType == right.returnType

        // A known identical result remains safe for an otherwise-known call
        // shape, including existing optional-parameter declarations. It does
        // not make unknown, literal/wide, or arity-ambiguous declarations safe.
        if (left.returnType == right.returnType) return true
        if (left.parameters.any { it.optional || it.variadic } || right.parameters.any { it.optional || it.variadic }) {
            return false
        }
        return left.parameters.zip(right.parameters).any { (leftParameter, rightParameter) ->
            definitelyDisjointTypes(leftParameter.type, rightParameter.type)
        }
    }

    private fun containsLiteralAndWideType(left: SageApiSignature, right: SageApiSignature): Boolean =
        left.parameters.zip(right.parameters).any { (leftParameter, rightParameter) ->
            (isLiteral(leftParameter.type) && isWideType(rightParameter.type)) ||
                (isLiteral(rightParameter.type) && isWideType(leftParameter.type))
        }

    private fun isLiteral(type: SageTypeRef): Boolean = type.expression?.startsWith("Literal[") == true

    private fun isWideType(type: SageTypeRef): Boolean =
        type.expression != null && !isLiteral(type) && !type.expression.contains("|")

    private fun sameParameterShape(left: SageApiSignature, right: SageApiSignature): Boolean =
        left.parameters.size == right.parameters.size && left.parameters.zip(right.parameters).all { (leftParameter, rightParameter) ->
            leftParameter.type == rightParameter.type &&
                leftParameter.optional == rightParameter.optional &&
                leftParameter.keywordOnly == rightParameter.keywordOnly &&
                leftParameter.variadic == rightParameter.variadic &&
                leftParameter.positionalOnly == rightParameter.positionalOnly
        }

    private fun definitelyDisjointTypes(left: SageTypeRef, right: SageTypeRef): Boolean {
        if (left.state != SageTypeState.KNOWN || right.state != SageTypeState.KNOWN) return false
        val leftExpression = left.expression ?: return false
        val rightExpression = right.expression ?: return false
        if (leftExpression == rightExpression) return false
        if (leftExpression.startsWith("Literal[") || rightExpression.startsWith("Literal[")) return false
        if (leftExpression.contains("|") || rightExpression.contains("|")) return false
        if (leftExpression in TEXT_TYPES && rightExpression in BYTE_TYPES) return true
        if (leftExpression in BYTE_TYPES && rightExpression in TEXT_TYPES) return true
        if (leftExpression in TEXT_TYPES && rightExpression in NUMERIC_TYPES) return true
        if (leftExpression in NUMERIC_TYPES && rightExpression in TEXT_TYPES) return true
        if (leftExpression in BYTE_TYPES && rightExpression in NUMERIC_TYPES) return true
        if (leftExpression in NUMERIC_TYPES && rightExpression in BYTE_TYPES) return true
        return false
    }

    private companion object {
        val TEXT_TYPES = setOf("str", "builtins.str")
        val BYTE_TYPES = setOf("bytes", "builtins.bytes")
        val NUMERIC_TYPES = setOf("int", "builtins.int", "float", "builtins.float", "complex", "builtins.complex")
    }

    private fun confidenceRank(value: SageApiConfidence): Int = when (value) {
        SageApiConfidence.HIGH -> 4
        SageApiConfidence.MEDIUM -> 3
        SageApiConfidence.LOW -> 2
        SageApiConfidence.UNKNOWN -> 1
    }
}
