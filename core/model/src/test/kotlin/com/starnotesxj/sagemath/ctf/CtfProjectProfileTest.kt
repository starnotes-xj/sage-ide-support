package com.starnotesxj.sagemath.ctf

import com.starnotesxj.sagemath.ctf.model.ExecutionTarget
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CtfProjectProfileTest {
    @Test
    fun `defaults are bounded and native`() {
        val profile = CtfProjectProfile("rsa")

        assertEquals(ExecutionTarget.Native, profile.executionTarget)
        assertEquals(CtfProjectProfile.DEFAULT_TIMEOUT_MILLIS, profile.timeoutMillis)
        assertEquals(CtfProjectProfile.DEFAULT_MAX_OUTPUT_BYTES, profile.maxOutputBytes)
    }

    @Test
    fun `invalid execution limits are rejected`() {
        assertFailsWith<IllegalArgumentException> {
            CtfProjectProfile("rsa", timeoutMillis = 0)
        }
        assertFailsWith<IllegalArgumentException> {
            CtfProjectProfile("rsa", maxOutputBytes = 0)
        }
    }
}
