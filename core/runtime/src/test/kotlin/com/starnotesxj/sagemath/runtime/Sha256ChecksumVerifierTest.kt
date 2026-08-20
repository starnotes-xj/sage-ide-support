package com.starnotesxj.sagemath.runtime

import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class Sha256ChecksumVerifierTest {
    @Test
    fun `known input produces lowercase sha256`() {
        val file = Files.createTempFile("sage-runtime-hash", ".bin")
        try {
            Files.writeString(file, "abc")
            val verifier = Sha256ChecksumVerifier()
            val digest = verifier.sha256(file)

            assertEquals(
                "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                digest,
            )
            assertTrue(verifier.verify(file, digest.uppercase()))
            assertFalse(verifier.verify(file, "0".repeat(64)))
        }
        finally {
            Files.deleteIfExists(file)
        }
    }
}
