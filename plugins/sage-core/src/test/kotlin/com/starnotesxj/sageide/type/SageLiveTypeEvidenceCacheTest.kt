package com.starnotesxj.sageide.type

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SageLiveTypeEvidenceCacheTest {
    @Test
    fun `evicts only the least recently used completed observation`() {
        val cache = SageLiveTypeEvidenceCache<String, String>(maximumEntries = 2, retryDelayMillis = 1_000)

        cache.recordSuccess("first", "A")
        cache.recordSuccess("second", "B")
        assertEquals("A", cache.completed("first"))
        cache.recordSuccess("third", "C")

        assertEquals("A", cache.completed("first"))
        assertNull(cache.completed("second"))
        assertEquals("C", cache.completed("third"))
    }

    @Test
    fun `failure backs off only its exact fingerprint and success clears the backoff`() {
        var now = 10_000L
        val cache = SageLiveTypeEvidenceCache<String, String>(maximumEntries = 2, retryDelayMillis = 500) { now }

        cache.recordFailure("bad")

        assertFalse(cache.maySchedule("bad"))
        assertTrue(cache.maySchedule("different-source"))
        now += 500
        assertTrue(cache.maySchedule("bad"))

        cache.recordFailure("bad")
        cache.recordSuccess("bad", "Integer")
        assertEquals("Integer", cache.completed("bad"))
        assertFalse(cache.maySchedule("bad"))
    }
}
