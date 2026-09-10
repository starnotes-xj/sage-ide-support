package com.starnotesxj.sagemath.runtime

import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.util.Base64
import java.util.Comparator
import java.util.UUID
import java.util.concurrent.TimeUnit
import org.junit.jupiter.api.Assumptions.assumeTrue
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull

class SageRunTypeFeedbackTest {
    @Test
    fun `decodes only the matching sidecar and preserves concrete MRO`() {
        fun encode(value: String): String = Base64.getEncoder().encodeToString(value.toByteArray(StandardCharsets.UTF_8))
        val record = "P|${encode("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field")}|" +
            encode("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field\u001fsage.structure.element.Element")
        val line = "${SageRunTypeFeedbackProtocol.MAGIC}\trun-1\tdigest-1\t${encode(record)}"

        val feedback = SageRunTypeFeedbackProtocol.decode(line, "run-1", "digest-1")

        assertEquals("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field", feedback?.observedTypes?.get("P")?.runtimeClass)
        assertEquals(listOf("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field", "sage.structure.element.Element"), feedback?.observedTypes?.get("P")?.methodResolutionOrder)
        assertNull(SageRunTypeFeedbackProtocol.decode(line, "other-run", "digest-1"))
        assertNull(SageRunTypeFeedbackProtocol.decode(line, "run-1", "other-digest"))
    }

    /**
     * Opt-in real WSL test. It proves that the sitecustomize hook leaves Sage's
     * normal file runner in place and receives globals from its actual namespace.
     */
    @Test
    fun `WSL Sage normal run writes concrete point feedback`() {
        assumeTrue(System.getProperty("sage.runFeedback.testWsl") == "true")
        val distribution = System.getProperty("sage.runFeedback.distribution", "Ubuntu")
        val executable = System.getProperty("sage.runFeedback.executable")
            ?: error("sage.runFeedback.executable is required when the WSL integration test is enabled")
        val directory = Files.createTempDirectory("sage-run-feedback-test-")
        try {
            val script = directory.resolve("sample.sage")
            val bootstrap = directory.resolve("sitecustomize.py")
            val response = directory.resolve("feedback.tsv")
            val source = """
                E = EllipticCurve(GF(11), [1, 1])
                P = E(0, 1)
                G = E.gen(0)
                g = gcd(12, 18)
            """.trimIndent() + "\n"
            Files.writeString(script, source, StandardCharsets.UTF_8)
            Files.writeString(bootstrap, SageRunTypeFeedbackProtocol.SITE_CUSTOMIZE_SOURCE, StandardCharsets.UTF_8)
            val runId = UUID.randomUUID().toString()
            val digest = sha256(source.toByteArray(StandardCharsets.UTF_8))
            val process = ProcessBuilder(
                "wsl.exe",
                "-d",
                distribution,
                "--exec",
                "/bin/sh",
                "-c",
                "PYTHONPATH=\"\${SAGE_IDE_RUN_TYPE_BOOTSTRAP}\${PYTHONPATH:+:\$PYTHONPATH}\"; export PYTHONPATH; exec \"\$@\"",
                "sage-ide-run-feedback-test",
                executable,
                "/mnt/${directory.root.toString().trimEnd('\\', '/').first().lowercaseChar()}/${directory.toString().drop(3).replace('\\', '/')}/sample.sage",
            ).apply {
                environment()[SageRunTypeFeedbackProtocol.BOOTSTRAP_PATH_ENV] = bootstrap.parent.toString()
                environment()[SageRunTypeFeedbackProtocol.OUTPUT_PATH_ENV] = response.toString()
                environment()[SageRunTypeFeedbackProtocol.RUN_ID_ENV] = runId
                environment()[SageRunTypeFeedbackProtocol.SOURCE_DIGEST_ENV] = digest
                environment()["WSLENV"] = listOf(
                    "${SageRunTypeFeedbackProtocol.BOOTSTRAP_PATH_ENV}/p",
                    "${SageRunTypeFeedbackProtocol.OUTPUT_PATH_ENV}/p",
                    "${SageRunTypeFeedbackProtocol.RUN_ID_ENV}/u",
                    "${SageRunTypeFeedbackProtocol.SOURCE_DIGEST_ENV}/u",
                ).joinToString(":")
                redirectErrorStream(true)
            }.start()
            val output = process.inputStream.bufferedReader(StandardCharsets.UTF_8).readText()
            assertEquals(true, process.waitFor(45, TimeUnit.SECONDS), output)
            assertEquals(0, process.exitValue(), output)
            assertFalse(output.contains(SageRunTypeFeedbackProtocol.MAGIC), output)

            val feedback = SageRunTypeFeedbackProtocol.decode(Files.readString(response, StandardCharsets.UTF_8), runId, digest)
            assertEquals("sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field", feedback?.observedTypes?.get("P")?.runtimeClass)
            assertEquals("sage.rings.integer.Integer", feedback?.observedTypes?.get("g")?.runtimeClass)
        } finally {
            // Sage can materialize an adjacent preparse cache below this exact
            // test-owned temp directory; remove no path outside that directory.
            Files.walk(directory).use { stream ->
                stream.sorted(Comparator.reverseOrder()).forEach { Files.deleteIfExists(it) }
            }
        }
    }

    private fun sha256(bytes: ByteArray): String = java.security.MessageDigest.getInstance("SHA-256")
        .digest(bytes)
        .joinToString("") { byte -> "%02x".format(byte) }
}
