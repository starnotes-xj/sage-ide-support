package com.starnotesxj.sagemath.sageapi

/** Read-only queries over the immutable, versioned Sage API index. */
class SageApiIndexQuery(val index: SageApiIndex) {
    fun find(qualifiedName: String, kind: SageApiSymbolKind? = null): SageApiEntry? =
        index.entries.firstOrNull { it.qualifiedName == qualifiedName && (kind == null || it.kind == kind) }

    /** Returns methods/properties/constants declared by the owner or its indexed parents. */
    fun members(ownerQualifiedName: String): List<SageApiEntry> {
        val owners = reachableTypeNames(ownerQualifiedName)
        return index.entries.asSequence()
            .filter { it.kind in MEMBER_KINDS }
            .filter { it.qualifiedName.substringBeforeLast('.', "") in owners }
            .sortedWith(compareBy<SageApiEntry> { it.qualifiedName.substringAfterLast('.') }
                .thenBy { it.kind.name }
                .thenBy { it.qualifiedName })
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

    /** Follows class aliases and parents without inventing a type for unknown data. */
    fun reachableTypeNames(observedName: String): Set<String> {
        val visited = linkedSetOf<String>()
        val pending = ArrayDeque<String>()
        pending.add(observedName)
        while (pending.isNotEmpty()) {
            val current = pending.removeFirst()
            if (!visited.add(current)) continue
            index.entries.asSequence()
                .filter { it.kind == SageApiSymbolKind.CLASS }
                .filter { it.qualifiedName == current || current in it.aliases }
                .forEach { entry ->
                    pending.add(entry.qualifiedName)
                    entry.aliases.forEach(pending::add)
                    entry.parents.forEach(pending::add)
                }
        }
        return visited
    }

    fun isKnownClassName(name: String): Boolean =
        index.entries.any { it.kind == SageApiSymbolKind.CLASS && (it.qualifiedName == name || name in it.aliases) }

    private companion object {
        val MEMBER_KINDS = setOf(SageApiSymbolKind.METHOD, SageApiSymbolKind.PROPERTY, SageApiSymbolKind.CONSTANT)
    }
}
