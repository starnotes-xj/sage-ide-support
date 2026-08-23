package com.starnotesxj.sagemath.sageapi

import java.util.concurrent.ConcurrentHashMap

/** Read-only, indexed queries over the immutable, versioned Sage API index. */
class SageApiIndexQuery(val index: SageApiIndex) {
    private val entriesByQualifiedName: Map<String, List<SageApiEntry>>
    private val entriesByOwner: Map<String, List<SageApiEntry>>
    private val entriesByNamespace: Map<String, List<SageApiEntry>>
    private val moduleEntriesByOwner: Map<String, List<SageApiEntry>>
    private val aliasesToEntries: Map<String, List<SageApiEntry>>
    private val entriesByShortName: Map<String, List<SageApiEntry>>
    private val classesByLookup: Map<String, List<SageApiEntry>>
    private val classesByShortName: Map<String, List<SageApiEntry>>
    private val functionsByLookup: Map<String, List<SageApiEntry>>
    private val functionsByShortName: Map<String, List<SageApiEntry>>
    private val reachableCache = ConcurrentHashMap<String, Map<String, Int>>()

    init {
        val byQualifiedName = linkedMapOf<String, MutableList<SageApiEntry>>()
        val byOwner = linkedMapOf<String, MutableList<SageApiEntry>>()
        val byNamespace = linkedMapOf<String, MutableList<SageApiEntry>>()
        val byModuleOwner = linkedMapOf<String, MutableList<SageApiEntry>>()
        val byAlias = linkedMapOf<String, MutableList<SageApiEntry>>()
        val byShortName = linkedMapOf<String, MutableList<SageApiEntry>>()
        val classLookup = linkedMapOf<String, MutableList<SageApiEntry>>()
        val classShortName = linkedMapOf<String, MutableList<SageApiEntry>>()
        val functionLookup = linkedMapOf<String, MutableList<SageApiEntry>>()
        val functionShortName = linkedMapOf<String, MutableList<SageApiEntry>>()

        for (entry in index.entries) {
            byQualifiedName.getOrPut(entry.qualifiedName) { mutableListOf() }.add(entry)
            entry.qualifiedName.substringBeforeLast('.', missingDelimiterValue = "").takeIf { it.isNotEmpty() }?.let { namespace ->
                byNamespace.getOrPut(namespace) { mutableListOf() }.add(entry)
            }
            byShortName.getOrPut(entry.qualifiedName.substringAfterLast('.')) { mutableListOf() }.add(entry)
            entry.aliases.forEach { alias ->
                byAlias.getOrPut(alias) { mutableListOf() }.add(entry)
            }
            // Keep every owned entry in this map: member queries filter to
            // MEMBER_KINDS, while module queries also need functions, classes,
            // and aliases exported directly by a module.
            entry.ownerName?.let { owner ->
                byOwner.getOrPut(owner) { mutableListOf() }.add(entry)
                byModuleOwner.getOrPut(owner) { mutableListOf() }.add(entry)
            }
            if (entry.kind == SageApiSymbolKind.CLASS) {
                addLookup(classLookup, entry.qualifiedName, entry)
                addLookup(classShortName, entry.qualifiedName.substringAfterLast('.'), entry)
                entry.aliases.forEach { addLookup(classLookup, it, entry) }
            }
            if (entry.kind == SageApiSymbolKind.FUNCTION) {
                addLookup(functionLookup, entry.qualifiedName, entry)
                addLookup(functionShortName, entry.qualifiedName.substringAfterLast('.'), entry)
                entry.aliases.forEach { addLookup(functionLookup, it, entry) }
            }
        }

        entriesByQualifiedName = freeze(byQualifiedName)
        entriesByOwner = freeze(byOwner)
        entriesByNamespace = freezeSorted(byNamespace)
        moduleEntriesByOwner = byModuleOwner.mapValues { (_, values) ->
            values.sortedWith(compareBy<SageApiEntry> { it.qualifiedName.substringAfterLast('.') }.thenBy { it.kind.name }).toList()
        }
        aliasesToEntries = freeze(byAlias)
        entriesByShortName = freeze(byShortName)
        classesByLookup = freeze(classLookup)
        classesByShortName = freeze(classShortName)
        functionsByLookup = freeze(functionLookup)
        functionsByShortName = freeze(functionShortName)
    }

    fun find(qualifiedName: String, kind: SageApiSymbolKind? = null): SageApiEntry? =
        findAll(qualifiedName, kind).firstOrNull()

    fun findAll(qualifiedName: String, kind: SageApiSymbolKind? = null): List<SageApiEntry> =
        entriesByQualifiedName[qualifiedName].orEmpty().filter { kind == null || it.kind == kind }

    /**
     * Resolves an indexed symbol by canonical name, alias, or an unambiguous
     * short name.  Dotted names never fall back to a short-name collision.
     */
    fun resolve(name: String, kind: SageApiSymbolKind? = null): SageApiEntry? {
        find(name, kind)?.let { return it }
        aliasesToEntries[name].orEmpty().firstOrNull { kind == null || it.kind == kind }?.let { return it }
        if ('.' !in name) {
            return entriesByShortName[name].orEmpty()
                .filter { kind == null || it.kind == kind }
                .distinctBy { it.qualifiedName to it.kind }
                .singleOrNull()
        }
        return null
    }

    /** Entries directly declared by a module or class owner. */
    fun entriesOwnedBy(ownerQualifiedName: String): List<SageApiEntry> =
        entriesByOwner[ownerQualifiedName].orEmpty()

    /**
     * Entries directly exported by a module, including functions/classes/aliases,
     * without scanning the complete index. A module entry itself has no owner;
     * only its child entries are returned.
     */
    fun moduleEntries(moduleQualifiedName: String): List<SageApiEntry> =
        moduleEntriesByOwner[moduleQualifiedName].orEmpty()

    /** Direct namespace declarations, including ownerless implicit sage.all API symbols. */
    fun namespaceEntries(namespaceQualifiedName: String): List<SageApiEntry> =
        entriesByNamespace[namespaceQualifiedName].orEmpty()

    /** Resolve one direct namespace export without consulting global short-name collisions. */
    fun namespaceEntry(namespaceQualifiedName: String, shortName: String): SageApiEntry? =
        namespaceEntries(namespaceQualifiedName)
            .filter { it.qualifiedName.substringAfterLast('.') == shortName }
            .singleOrNull()

    /** Returns methods/properties/constants declared by the owner or its indexed parents. */
    fun members(ownerQualifiedName: String): List<SageApiEntry> {
        val ownerRanks = reachableTypeRanks(ownerQualifiedName)
        return ownerRanks.asSequence()
            .flatMap { (owner, rank) ->
                entriesByOwner[owner].orEmpty().asSequence()
                    .filter { it.kind in MEMBER_KINDS }
                    .map { rank to it }
            }
            .sortedWith(
                compareBy<Pair<Int, SageApiEntry>> { it.second.qualifiedName.substringAfterLast('.') }
                    .thenBy { it.second.kind.name }
                    .thenBy { it.first }
                    .thenBy { it.second.qualifiedName },
            )
            .map { it.second }
            .distinctBy { it.qualifiedName.substringAfterLast('.') to it.kind }
            .toList()
    }

    fun members(ownerQualifiedName: String, memberName: String): List<SageApiEntry> =
        members(ownerQualifiedName).filter { it.qualifiedName.substringAfterLast('.') == memberName }

    /**
     * Return references for a callable name, alias, or unambiguous method.
     * The result preserves UNKNOWN/DYNAMIC states; callers must use
     * [uniqueKnownReturnType] before assignment propagation.
     */
    fun callReturnTypes(callableQualifiedName: String): List<SageTypeRef> =
        (functionEntries(callableQualifiedName) + listOfNotNull(resolve(callableQualifiedName)))
            .distinctBy { it.qualifiedName to it.kind }
            .flatMap { it.signatures.asSequence() }
            .map { it.returnType }
            .distinct()

    /**
     * Indexed signatures for a canonical name or alias, including methods.
     * Function lookup preserves unqualified overload behavior; resolve adds the
     * unambiguous method/property case without inventing a symbol on collisions.
     */
    fun signatures(symbolQualifiedName: String): List<SageApiSignature> =
        (functionEntries(symbolQualifiedName) + listOfNotNull(resolve(symbolQualifiedName)))
            .distinctBy { it.qualifiedName to it.kind }
            .flatMap { it.signatures }

    /** Best available documentation for a canonical name or alias. */
    fun documentation(qualifiedName: String): SageApiDocumentation? =
        resolve(qualifiedName)?.documentation

    /** Only precise, unique return types are safe for assignment propagation. */
    fun uniqueKnownReturnType(functionQualifiedName: String): SageTypeRef? {
        val returns = callReturnTypes(functionQualifiedName)
        if (returns.isEmpty() || returns.any { type ->
                type.state != SageTypeState.KNOWN ||
                    type.expression.isNullOrBlank() ||
                    type.expression.contains('|')
            }) return null
        return returns.distinctBy { it.expression }.singleOrNull()
    }

    /** Resolve a known class expression to one canonical indexed class name. */
    fun resolveKnownClassName(typeExpression: String): String? {
        val normalized = typeExpression.substringBefore('[').trim()
        if (normalized.isBlank()) return null
        val exact = classEntries(normalized).map { it.qualifiedName }.distinct()
        if (exact.size == 1) return exact.single()
        if (exact.size > 1 || '.' in normalized) return null
        return classesByShortName[normalized].orEmpty().map { it.qualifiedName }.distinct().singleOrNull()
    }

    /** Follows class aliases and parents without inventing a type for unknown data. */
    fun reachableTypeNames(observedName: String): Set<String> = reachableTypeRanks(observedName).keys

    private fun reachableTypeRanks(observedName: String): Map<String, Int> =
        reachableCache.computeIfAbsent(observedName) {
            val ranks = linkedMapOf<String, Int>()
            val pending = ArrayDeque<Pair<String, Int>>()
            pending.add(observedName to 0)
            while (pending.isNotEmpty()) {
                val (current, rank) = pending.removeFirst()
                val previous = ranks[current]
                if (previous != null && previous <= rank) continue
                ranks[current] = rank
                classEntries(current).forEach { entry ->
                    pending.add(entry.qualifiedName to rank)
                    entry.aliases.forEach { pending.add(it to rank) }
                    entry.parents.forEach { pending.add(it to rank + 1) }
                }
            }
            ranks
        }

    fun isKnownClassName(name: String): Boolean = classEntries(name).isNotEmpty()

    private fun functionEntries(name: String): List<SageApiEntry> {
        val direct = functionsByLookup[name].orEmpty()
        if ('.' in name) return direct.distinctBy { it.qualifiedName to it.kind }
        // Preserve the original query contract: an unqualified function name
        // considers both an exact/alias match and every short-name candidate.
        return (direct + functionsByShortName[name].orEmpty())
            .distinctBy { it.qualifiedName to it.kind }
    }

    /** Canonical/alias class entries; short-name fallback is caller-specific. */
    private fun classEntries(name: String): List<SageApiEntry> =
        classesByLookup[name].orEmpty().distinctBy { it.qualifiedName to it.kind }

    private companion object {
        val MEMBER_KINDS = setOf(SageApiSymbolKind.METHOD, SageApiSymbolKind.PROPERTY, SageApiSymbolKind.CONSTANT)

        fun addLookup(target: MutableMap<String, MutableList<SageApiEntry>>, key: String, entry: SageApiEntry) {
            target.getOrPut(key) { mutableListOf() }.add(entry)
        }

        fun freeze(source: Map<String, MutableList<SageApiEntry>>): Map<String, List<SageApiEntry>> =
            source.mapValues { (_, values) -> values.toList() }

        fun freezeSorted(source: Map<String, MutableList<SageApiEntry>>): Map<String, List<SageApiEntry>> =
            source.mapValues { (_, values) ->
                values.sortedWith(compareBy<SageApiEntry> { it.qualifiedName.substringAfterLast('.') }.thenBy { it.kind.name })
            }
    }
}
