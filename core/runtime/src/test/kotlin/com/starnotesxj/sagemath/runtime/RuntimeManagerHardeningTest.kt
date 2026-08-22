package com.starnotesxj.sagemath.runtime

import java.net.URI
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RuntimeManagerHardeningTest {
    private val platform = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.X64, Libc.GLIBC)

    @Test
    fun `built in production verifier does not trust test signing key`() {
        val document = RuntimeCatalogDocument(
            "official",
            artifacts = listOf(artifact()),
        )
        val envelope = signWithTestKey(document)

        val result = RuntimeCatalogSignatureVerifier().verify(envelope)

        assertFalse(result.valid)
        assertTrue(result.diagnostics.any { it.code == RuntimeDiagnosticCode.CATALOG_KEY_UNTRUSTED })
    }

    @Test
    fun `lifecycle rejects runtime directory renamed away from manifest identity`() {
        val root = Files.createTempDirectory("sage-runtime-identity")
        try {
            val id = SageRuntimeId("10.6", platform)
            val runtimeRoot = root.resolve("versions").resolve("unrelated-name")
            Files.createDirectories(runtimeRoot)
            val executable = runtimeRoot.resolve("sage")
            Files.writeString(executable, "sage")
            val manifest = RuntimeManifest(
                1,
                id,
                "sage",
                listOf(RuntimeFileRecord("sage", 4, Sha256ChecksumVerifier().sha256(executable))),
                "0".repeat(64),
            )
            Files.write(root.resolve("versions/.unrelated-name.meta"), RuntimeManifestCodec.encode(manifest))
            Files.writeString(root.resolve("current"), "unrelated-name")

            val result = FileRuntimeLifecycle(root).current()

            assertFalse(result.succeeded)
            assertTrue(result.diagnostics.any { it.code == RuntimeDiagnosticCode.CURRENT_RUNTIME_INVALID })
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `signed envelope rejects oversized fields before document parsing`() {
        val key = "test-key"
        val oversizedKey = "keyId=" + java.util.Base64.getUrlEncoder().withoutPadding()
            .encodeToString(ByteArray(SignedRuntimeCatalogCodec.MAX_ENCODED_BYTES))
        val bytes = "schemaVersion=1\n$oversizedKey\ndocument=YQ\nsignature=YQ\n".toByteArray()

        assertFailsWith<IllegalArgumentException> {
            SignedRuntimeCatalogCodec.decode(bytes)
        }
    }

    @Test
    fun `target executor runs WSL and Docker locally while SSH remains remote`() {
        val localCommands = mutableListOf<List<String>>()
        val remoteRequests = mutableListOf<TargetProcessRequest>()
        val local = RuntimeProcessExecutor { request ->
            localCommands += request.command
            RuntimeProcessResult(RuntimeExecutionStatus.SUCCESS, 0, "", "", 1, false)
        }
        val executor = JdkRuntimeTargetExecutor(local) { request ->
            remoteRequests += request
            RuntimeProcessResult(RuntimeExecutionStatus.SUCCESS, 0, "", "", 1, false)
        }

        executor.execute(TargetProcessRequest(RuntimeTarget.Wsl("Ubuntu"), "/sage", listOf("--version")))
        executor.execute(TargetProcessRequest(RuntimeTarget.Docker("sage:latest"), "/sage", listOf("--version")))
        executor.execute(TargetProcessRequest(RuntimeTarget.RemoteSsh("host"), "/sage", listOf("--version")))

        assertEquals(listOf("wsl.exe", "-d", "Ubuntu", "--", "/sage", "--version"), localCommands[0])
        assertEquals(listOf("docker", "run", "--rm", "sage:latest", "/sage", "--version"), localCommands[1])
        assertTrue(remoteRequests.single().target is RuntimeTarget.RemoteSsh)
    }

    @Test
    fun `path mapper rejects UNC and native traversal`() {
        val mapping = RuntimePathMapping(Path.of("/workspace"), "/mnt/workspace")
        val mapper = RuntimePathMapper()

        assertFailsWith<IllegalArgumentException> {
            mapper.toLocal("//server/share/file", RuntimeTarget.Wsl("Ubuntu", mapping))
        }
        assertFailsWith<IllegalArgumentException> {
            mapper.toLocal("/mnt/workspace/../escape", RuntimeTarget.Wsl("Ubuntu", mapping))
        }
    }

    private fun artifact() = RuntimeArtifact(
        SageRuntimeId("10.6", platform),
        URI("https://example.invalid/sage.zip"),
        ArchiveFormat.ZIP,
        sha256 = "0".repeat(64),
    )

    private fun signWithTestKey(document: RuntimeCatalogDocument): RuntimeCatalogEnvelope {
        val privateKey = java.security.KeyFactory.getInstance("Ed25519").generatePrivate(
            java.security.spec.EdECPrivateKeySpec(
                java.security.spec.NamedParameterSpec.ED25519,
                "1d73641dfef55688c6faf84c2c8894e7e82d2b97b587f53df2aac5932286b478"
                    .chunked(2).map { it.toInt(16).toByte() }.toByteArray(),
            ),
        )
        val signature = java.security.Signature.getInstance("Ed25519").apply {
            initSign(privateKey)
            update(RuntimeCatalogCodec.encode(document))
        }.sign()
        return RuntimeCatalogEnvelope(document, "test-key", signature)
    }

    private fun deleteTree(root: Path) {
        if (!Files.exists(root)) return
        Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
    }
}
