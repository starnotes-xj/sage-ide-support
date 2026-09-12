package com.starnotesxj.sageide.type

import java.util.LinkedHashMap

/**
 * Bounded, in-memory evidence cache for one live Sage session.
 *
 * A value is an observation for one exact source/runtime fingerprint; it is
 * never a generalized Sage contract.  Failed fingerprints are held only for a
 * short retry window so an incomplete document or a deterministic Sage error
 * cannot continuously restart a background worker while the daemon reruns.
 */
internal class SageLiveTypeEvidenceCache<K : Any, V : Any>(
    private val maximumEntries: Int,
    private val retryDelayMillis: Long,
    private val nowMillis: () -> Long = System::currentTimeMillis,
) {
    init {
        require(maximumEntries > 0) { "Live type evidence cache size must be positive" }
        require(retryDelayMillis > 0) { "Live type evidence retry delay must be positive" }
    }

    private val completed = object : LinkedHashMap<K, V>(maximumEntries, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<K, V>?): Boolean = size > maximumEntries
    }
    private val retryAfter = object : LinkedHashMap<K, Long>(maximumEntries, 0.75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<K, Long>?): Boolean = size > maximumEntries
    }

    @Synchronized
    fun completed(key: K): V? = completed[key]

    /**
     * Returns a stable snapshot for the rare case where a caller must choose
     * between several exact observations using stronger local evidence.
     */
    @Synchronized
    fun completedEntries(): List<Pair<K, V>> = completed.entries.map { it.key to it.value }

    @Synchronized
    fun maySchedule(key: K): Boolean =
        !completed.containsKey(key) && (retryAfter[key] ?: Long.MIN_VALUE) <= nowMillis()

    @Synchronized
    fun recordSuccess(key: K, value: V) {
        completed[key] = value
        retryAfter.remove(key)
    }

    @Synchronized
    fun recordFailure(key: K) {
        retryAfter[key] = nowMillis() + retryDelayMillis
    }

    @Synchronized
    fun clear() {
        completed.clear()
        retryAfter.clear()
    }
}
