package com.starnotesxj.sagemath.sageapi

import java.util.LinkedHashMap

/** Read-only, indexed queries over the immutable, versioned Sage API index. */
class SageApiIndexQuery(val index: SageApiIndex) {
    private val entriesByQualifiedName: Map<String, List<SageApiEntry>>
    private val entriesByOwner: Map<String, List<SageApiEntry>>
    private val entriesByNamespace: Map<String, List<SageApiEntry>>
    private val aliasesToEntries: Map<String, List<SageApiEntry>>
    private val entriesByShortName: Map<String, List<SageApiEntry>>
    private val classesByLookup: Map<String, List<SageApiEntry>>
    private val classesByShortName: Map<String, List<SageApiEntry>>
    private val functionsByLookup: Map<String, List<SageApiEntry>>
    private val functionsByShortName: Map<String, List<SageApiEntry>>
    // The full index has many concrete classes. These are lookup accelerators,
    // not authoritative data, so they must stay bounded during long CTF
    // sessions that visit many dynamically generated receiver types.
    private val reachableCache = BoundedLruCache<String, Map<String, Int>>(MAX_CACHED_TYPE_GRAPHS)
    private val linearizationCache = BoundedLruCache<String, List<String>>(MAX_CACHED_TYPE_GRAPHS)

    init {
        val byQualifiedName = linkedMapOf<String, MutableList<SageApiEntry>>()
        val byOwner = linkedMapOf<String, MutableList<SageApiEntry>>()
        val byNamespace = linkedMapOf<String, MutableList<SageApiEntry>>()
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
        // Module export and member queries are both owner lookups. Keeping two
        // complete maps duplicated every full-index entry and retained a large
        // amount of heap for no semantic gain. A stable sorted owner map serves
        // both use cases; member lookup continues to apply its own C3 ordering.
        entriesByOwner = freezeSorted(byOwner)
        entriesByNamespace = freezeSorted(byNamespace)
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
        entriesByOwner[moduleQualifiedName].orEmpty()

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
        // Use an indexed C3 order rather than only breadth-first ranks.  A rank
        // is enough for reachability, but it cannot distinguish sibling bases in
        // a diamond.  Python resolves one attribute name to the nearest owner,
        // regardless of whether the competing metadata kinds differ.
        val selected = linkedMapOf<String, MutableList<SageApiEntry>>()
        for (owner in linearizedTypeNames(ownerQualifiedName)) {
            entriesByOwner[owner].orEmpty()
                .asSequence()
                .filter { it.kind in MEMBER_KINDS }
                .sortedWith(compareBy<SageApiEntry> { it.qualifiedName.substringAfterLast('.') }.thenBy { it.kind.name })
                .forEach { entry ->
                    val memberName = entry.qualifiedName.substringAfterLast('.')
                    // Keep every declaration for the nearest owner.  METHOD and
                    // PROPERTY pairs are both legitimate in generated Sage stubs
                    // (a setter plus a getter), and query completeness must not
                    // lose one merely because completion later chooses a view.
                    selected.getOrPut(memberName) { mutableListOf() }.also { bucket ->
                        if (bucket.isEmpty() || bucket.first().ownerName == entry.ownerName) bucket += entry
                    }
                }
        }
        return selected.values
            .flatten()
            .sortedWith(compareBy<SageApiEntry> { it.qualifiedName.substringAfterLast('.') }.thenBy { it.kind.name })
    }

    /**
     * Computes the metadata-only Python MRO for one class.  Ambiguous class
     * aliases and inconsistent/cyclic parent graphs stop at the known owner;
     * they never cause a parent member to be fabricated or selected randomly.
     */
    private fun linearizedTypeNames(observedName: String): List<String> = linearizationCache.getOrPut(observedName) {
        val resolved = classEntries(observedName).map { it.qualifiedName }.distinct()
        if (resolved.size > 1) return@getOrPut listOf(observedName)
        val start = resolved.singleOrNull() ?: observedName
        val memo = mutableMapOf<String, List<String>>()
        val active = mutableSetOf<String>()

        fun mergeC3(sequences: List<List<String>>): List<String>? {
            val work = sequences.map { it.toMutableList() }.toMutableList()
            val result = mutableListOf<String>()
            while (work.any { it.isNotEmpty() }) {
                val candidate = work.asSequence()
                    .mapNotNull { it.firstOrNull() }
                    .distinct()
                    .firstOrNull { head -> work.none { head in it.drop(1) } }
                    ?: return null
                result += candidate
                work.forEach { sequence ->
                    if (sequence.firstOrNull() == candidate) sequence.removeAt(0)
                }
            }
            return result
        }

        fun linearize(name: String): List<String> {
            val canonical = classEntries(name).map { it.qualifiedName }.distinct().singleOrNull() ?: name
            memo[canonical]?.let { return it }
            if (!active.add(canonical)) return listOf(canonical)
            val entry = classEntries(canonical).singleOrNull { it.qualifiedName == canonical }
            val parents = entry?.parents.orEmpty()
                .flatMap { parent ->
                    val candidates = classEntries(parent).map { it.qualifiedName }.distinct()
                    when {
                        candidates.size == 1 -> candidates
                        candidates.isEmpty() -> listOf(parent)
                        else -> emptyList()
                    }
                }
                .filterNot { it in active }
                .distinct()
            val sequences = parents.map(::linearize) + listOf(parents)
            val merged = mergeC3(sequences)
            val result = if (merged == null) listOf(canonical) else listOf(canonical) + merged
            active.remove(canonical)
            memo[canonical] = result.distinct()
            return memo.getValue(canonical)
        }

        linearize(start)
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

    /** Returns one unanimous trusted KNOWN return proof for this exact signature. */
    fun uniqueTrustedKnownReturnExpression(signature: SageApiSignature): SageTypeRef? {
        val evidence = signature.trustedReturnEvidence
        if (evidence.isEmpty() || evidence.any { it.returnType.state != SageTypeState.KNOWN || it.returnType.expression.isNullOrBlank() }) {
            return null
        }
        return evidence
            .map { SageTypeRef.known(it.returnType.expression!!.trim()) }
            .distinctBy { it.expression }
            .singleOrNull()
    }

    /**
     * Returns one complete known return expression when every indexed overload
     * agrees. Unlike [uniqueKnownReturnType], this preserves generic, union,
     * Optional, Literal, and Callable structure for the PSI lowering layer.
     */
    fun uniqueKnownReturnExpression(functionQualifiedName: String): SageTypeRef? {
        val returns = callReturnTypes(functionQualifiedName)
        if (returns.isEmpty() || returns.any { type ->
                type.state != SageTypeState.KNOWN || type.expression.isNullOrBlank()
            }) return null
        return returns
            .map { type -> SageTypeRef.known(type.expression!!.trim()) }
            .distinctBy { it.expression }
            .singleOrNull()
    }

    /** Only precise, unique simple/class return types are safe for legacy callers. */
    fun uniqueKnownReturnType(functionQualifiedName: String): SageTypeRef? {
        val type = uniqueKnownReturnExpression(functionQualifiedName) ?: return null
        val expression = parseTypeExpression(type) ?: return null
        if (expression is SageTypeExpression.Union ||
            expression is SageTypeExpression.Optional ||
            expression is SageTypeExpression.Callable
        ) return null
        if (expression is SageTypeExpression.NoneType) return type
        if (expression is SageTypeExpression.Literal) return type
        if (expression is SageTypeExpression.Generic) {
            return type.takeIf { expression.base.qualifiedName != "typing.Union" && expression.base.qualifiedName != "typing.Optional" }
        }
        if (expression !is SageTypeExpression.Name) return null
        return type.takeIf { !it.expression.orEmpty().contains('|') }
    }

    /** Parse a known type expression without silently discarding generic/union structure. */
    fun parseTypeExpression(type: SageTypeRef): SageTypeExpression? =
        SageTypeRefExpressionParser.parse(type)

    fun parseTypeExpression(expression: String): SageTypeExpression? =
        SageTypeRefExpressionParser.parse(expression)

    /** Resolve a simple known class expression to one canonical indexed class name. */
    fun resolveKnownClassName(typeExpression: String): String? {
        val expression = parseTypeExpression(typeExpression) ?: return null
        val normalized = when (expression) {
            is SageTypeExpression.Name -> expression.qualifiedName
            is SageTypeExpression.Generic -> expression.base.qualifiedName
            else -> return null
        }.trim()
        if (normalized.isBlank()) return null
        val exact = classEntries(normalized).map { it.qualifiedName }.distinct()
        if (exact.size == 1) return exact.single()
        if (exact.size > 1 || '.' in normalized) return null
        return classesByShortName[normalized].orEmpty().map { it.qualifiedName }.distinct().singleOrNull()
    }

    /** Follows class aliases and parents without inventing a type for unknown data. */
    fun reachableTypeNames(observedName: String): Set<String> = reachableTypeRanks(observedName).keys

    private fun reachableTypeRanks(observedName: String): Map<String, Int> =
        reachableCache.getOrPut(observedName) {
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
        const val MAX_CACHED_TYPE_GRAPHS = 1_024

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

/** A small synchronized LRU for derived query results over an immutable index. */
private class BoundedLruCache<K : Any, V : Any>(maximumEntries: Int) {
    init {
        require(maximumEntries > 0) { "LRU cache size must be positive" }
    }

    private val values = object : LinkedHashMap<K, V>(maximumEntries, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<K, V>?): Boolean = size > maximumEntries
    }

    fun getOrPut(key: K, compute: () -> V): V = synchronized(values) {
        values[key] ?: compute().also { values[key] = it }
    }
}
