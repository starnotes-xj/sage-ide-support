package com.starnotesxj.sagemath.sageapi

/** Read-only queries over the immutable, versioned Sage API index. */
class SageApiIndexQuery(val index: SageApiIndex) {
    fun find(qualifiedName: String, kind: SageApiSymbolKind? = null): SageApiEntry? =
        index.entries.firstOrNull { it.qualifiedName == qualifiedName && (kind == null || it.kind == kind) }

    fun findAll(qualifiedName: String, kind: SageApiSymbolKind? = null): List<SageApiEntry> =
        index.entries.filter { it.qualifiedName == qualifiedName && (kind == null || it.kind == kind) }

    /** Returns methods/properties/constants declared by the owner or its indexed parents. */
    fun members(ownerQualifiedName: String): List<SageApiEntry> {
        val ownerRanks = reachableTypeRanks(ownerQualifiedName)
        return index.entries.asSequence()
            .filter { it.kind in MEMBER_KINDS }
            .mapNotNull { entry ->
                val owner = entry.qualifiedName.substringBeforeLast('.', "")
                ownerRanks[owner]?.let { rank -> rank to entry }
            }
            .sortedWith(compareBy<Pair<Int, SageApiEntry>> { it.second.qualifiedName.substringAfterLast('.') }
                .thenBy { it.second.kind.name }
                .thenBy { it.first }
                .thenBy { it.second.qualifiedName })
            .map { it.second }
            .distinctBy { it.qualifiedName.substringAfterLast('.') to it.kind }
            .toList()
    }

    fun members(ownerQualifiedName: String, memberName: String): List<SageApiEntry> =
        members(ownerQualifiedName).filter { it.qualifiedName.substringAfterLast('.') == memberName }

    /** Known return references for all indexed overloads of a function or alias. */
    fun callReturnTypes(functionQualifiedName: String): List<SageTypeRef> =
        index.entries.asSequence()
            .filter { it.kind == SageApiSymbolKind.FUNCTION }
            .filter { it.qualifiedName == functionQualifiedName || functionQualifiedName in it.aliases }
            .flatMap { it.signatures.asSequence() }
            .map { it.returnType }
            .distinct()
            .toList()

    /** Only precise, unique return types are safe for assignment propagation. */
    fun uniqueKnownReturnType(functionQualifiedName: String): SageTypeRef? {
        val returns = callReturnTypes(functionQualifiedName)
        if (returns.isEmpty() || returns.any { it.state != SageTypeState.KNOWN || it.expression.isNullOrBlank() }) return null
        return returns.distinctBy { it.expression }.singleOrNull()
    }

    /** Resolve a known class expression to one canonical indexed class name. */
    fun resolveKnownClassName(typeExpression: String): String? {
        val normalized = typeExpression.substringBefore('[').trim()
        if (normalized.isBlank()) return null
        val exact = index.entries.filter {
            it.kind == SageApiSymbolKind.CLASS && (it.qualifiedName == normalized || normalized in it.aliases)
        }.map { it.qualifiedName }.distinct()
        if (exact.size == 1) return exact.single()
        if (exact.size > 1) return null
        if ('.' in normalized) return null
        val simple = normalized
        return index.entries.asSequence()
            .filter { it.kind == SageApiSymbolKind.CLASS && it.qualifiedName.substringAfterLast('.') == simple }
            .map { it.qualifiedName }
            .distinct()
            .singleOrNull()
    }

    /** Follows class aliases and parents without inventing a type for unknown data. */
    fun reachableTypeNames(observedName: String): Set<String> = reachableTypeRanks(observedName).keys

    private fun reachableTypeRanks(observedName: String): Map<String, Int> {
        val ranks = linkedMapOf<String, Int>()
        val pending = ArrayDeque<Pair<String, Int>>()
        pending.add(observedName to 0)
        while (pending.isNotEmpty()) {
            val (current, rank) = pending.removeFirst()
            val previous = ranks[current]
            if (previous != null && previous <= rank) continue
            ranks[current] = rank
            index.entries.asSequence()
                .filter { it.kind == SageApiSymbolKind.CLASS }
                .filter { it.qualifiedName == current || current in it.aliases }
                .forEach { entry ->
                    pending.add(entry.qualifiedName to rank)
                    entry.aliases.forEach { pending.add(it to rank) }
                    entry.parents.forEach { pending.add(it to rank + 1) }
                }
        }
        return ranks
    }

    fun isKnownClassName(name: String): Boolean =
        index.entries.any { it.kind == SageApiSymbolKind.CLASS && (it.qualifiedName == name || name in it.aliases) }

    private companion object {
        val MEMBER_KINDS = setOf(SageApiSymbolKind.METHOD, SageApiSymbolKind.PROPERTY, SageApiSymbolKind.CONSTANT)
    }
}
