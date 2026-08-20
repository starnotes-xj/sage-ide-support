package com.starnotesxj.sagemath.ctf

import com.starnotesxj.sagemath.ctf.model.ExecutionTarget
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class CtfProjectProfileTest {
    @Test
    fun `defaults are unlimited and native`() {
        val profile = CtfProjectProfile("rsa")

        assertEquals(ExecutionTarget.Native, profile.executionTarget)
        assertEquals(null, profile.timeoutMillis)
        assertEquals(CtfProjectProfile.DEFAULT_MAX_OUTPUT_BYTES, profile.maxOutputBytes)
    }

    @Test
    fun `positive timeout remains opt in`() {
        val profile = CtfProjectProfile("rsa", timeoutMillis = 90_000)

        assertEquals(90_000, profile.timeoutMillis)
    }

    @Test
    fun `null timeout explicitly means unlimited`() {
        assertEquals(null, CtfProjectProfile("rsa", timeoutMillis = null).timeoutMillis)
    }

    @Test
    fun `zero and negative timeout are rejected`() {
        assertFailsWith<IllegalArgumentException> {
            CtfProjectProfile("rsa", timeoutMillis = 0)
        }
        assertFailsWith<IllegalArgumentException> {
            CtfProjectProfile("rsa", timeoutMillis = -1)
        }
    }

    @Test
    fun `invalid output limit is rejected`() {
        assertFailsWith<IllegalArgumentException> {
            CtfProjectProfile("rsa", maxOutputBytes = 0)
        }
    }
}
