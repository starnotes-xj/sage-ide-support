package com.starnotesxj.sagemath.runtime

import java.net.URI
import java.nio.file.Files
import java.nio.file.Path
import java.security.KeyFactory
import java.security.PrivateKey
import java.security.spec.EdECPrivateKeySpec
import java.security.spec.NamedParameterSpec
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class RuntimeManagerFeatureTest {
    private val platform = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.X64, Libc.GLIBC)
    // Test-only key is unrelated to the production public key; it is not accepted by the built-in trust store.
    private val seed = "1d73641dfef55688c6faf84c2c8894e7" +
        "e82d2b97b587f53df2aac5932286b478"

    @Test
    fun `built in Ed25519 key verifies a canonical signed catalog`() {
        val artifact = artifact("10.6", "https://mirror.example.invalid/sage.zip")
        val document = RuntimeCatalogDocument(
            catalogId = "official",
            generatedAt = java.time.Instant.parse("2026-01-01T00:00:00Z"),
            artifacts = listOf(artifact),
        )
        val envelope = signed(document)

        val encoded = SignedRuntimeCatalogCodec.encode(envelope)
        val decoded = SignedRuntimeCatalogCodec.decode(encoded)
        val result = testVerifier().verify(decoded)

        assertTrue(result.valid)
        assertEquals(document, result.document)
        assertTrue(result.diagnostics.isEmpty())
    }

    @Test
    fun `catalog signature verification fails closed on tampering and unknown key`() {
        val document = RuntimeCatalogDocument(
            catalogId = "official",
            artifacts = listOf(artifact("10.6", "https://mirror.example.invalid/sage.zip")),
        )
        val original = signed(document)
        val tampered = original.copy(
            document = document.copy(artifacts = listOf(artifact("10.7", "https://mirror.example.invalid/sage.zip"))),
        )
        val badKey = original.copy(keyId = "attacker-key")

        val tamperedResult = testVerifier().verify(tampered)
        val badKeyResult = testVerifier().verify(badKey)

        assertFalse(tamperedResult.valid)
        assertEquals(RuntimeDiagnosticCode.CATALOG_SIGNATURE_INVALID, tamperedResult.diagnostics.single().code)
        assertFalse(badKeyResult.valid)
        assertEquals(RuntimeDiagnosticCode.CATALOG_KEY_UNTRUSTED, badKeyResult.diagnostics.single().code)
    }

    @Test
    fun `service composition keeps installer and lifecycle on one install root`() {
        val root = Files.createTempDirectory("sage-runtime-service-composition")
        try {
            val id = SageRuntimeId("10.6", platform)
            val document = RuntimeCatalogDocument("test", artifacts = listOf(artifact("10.6", "https://mirror.example.invalid/sage.zip")))
            val catalog = StaticRuntimeCatalog(listOf(artifact("10.6", "https://mirror.example.invalid/sage.zip")))
            val installer = object : RuntimeInstaller {
                override fun install(request: RuntimeInstallRequest): InstallResult {
                    assertEquals(root.toAbsolutePath().normalize(), request.installRoot.toAbsolutePath().normalize())
                    return InstallResult.Failed("TEST", RuntimeInstallException("TEST", "stop"), cleanupPerformed = true)
                }
            }
            val service = SageRuntimeManager(
                catalog = catalog,
                installer = installer,
                locator = FileRuntimeLocator(),
                installRoot = root,
            )
            val selectedArtifact = service.available(RuntimeQuery(platform = platform)).single()
            assertEquals(id, selectedArtifact.id)
            val manifest = RuntimeManifest(
                schemaVersion = 1,
                runtimeId = id,
                executable = "bin/sage",
                files = listOf(RuntimeFileRecord("bin/sage", 1, "0".repeat(64))),
                artifactSha256 = selectedArtifact.sha256,
            )
            val result = service.install(selectedArtifact, manifest)
            assertTrue(result is InstallResult.Failed)
            assertEquals("TEST", result.stage)
            assertEquals(null, service.locate(id))
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `remote catalog uses verified mirror and then verified offline cache`() {
        val document = RuntimeCatalogDocument(
            catalogId = "official",
            artifacts = listOf(artifact("10.6", "https://mirror.example.invalid/sage.zip")),
        )
        val envelope = signed(document)
        val primary = URI("https://catalog.example.invalid/runtime.catalog")
        val mirror = URI("https://mirror.example.invalid/runtime.catalog")
        val responses = mutableMapOf(mirror to SignedRuntimeCatalogCodec.encode(envelope))
        val source = RuntimeCatalogSource { uri, _ ->
            responses[uri] ?: throw RuntimeCatalogFetchException("NETWORK_ERROR", "offline")
        }
        val cache = Files.createTempDirectory("sage-runtime-catalog").resolve("catalog.cache")
        try {
            val loader = SignedRuntimeCatalogLoader(source, testVerifier(), cache)
            val fromMirror = loader.load(primary, mirrors = listOf(mirror))
            assertTrue(fromMirror.succeeded)
            assertEquals(RuntimeCatalogLoadSource.MIRROR, fromMirror.source)
            assertTrue(Files.isRegularFile(cache))

            responses.clear()
            val fromCache = loader.load(primary, mirrors = listOf(mirror))
            assertTrue(fromCache.succeeded)
            assertEquals(RuntimeCatalogLoadSource.CACHE, fromCache.source)
            assertEquals(document, fromCache.document)
        }
        finally {
            Files.deleteIfExists(cache)
            Files.deleteIfExists(cache.parent)
        }
    }

    @Test
    fun `invalid remote catalog cannot replace or become an installable cache`() {
        val document = RuntimeCatalogDocument(
            catalogId = "official",
            artifacts = listOf(artifact("10.6", "https://mirror.example.invalid/sage.zip")),
        )
        val invalid = signed(document).copy(
            document = document.copy(artifacts = listOf(artifact("10.7", "https://mirror.example.invalid/sage.zip"))),
        )
        val uri = URI("https://catalog.example.invalid/runtime.catalog")
        val cache = Files.createTempDirectory("sage-runtime-invalid-catalog").resolve("catalog.cache")
        try {
            val source = RuntimeCatalogSource { _, _ -> SignedRuntimeCatalogCodec.encode(invalid) }
            val result = SignedRuntimeCatalogLoader(source, testVerifier(), cache).load(uri)
            assertFalse(result.succeeded)
            assertTrue(result.diagnostics.any { it.code == RuntimeDiagnosticCode.CATALOG_SIGNATURE_INVALID })
            assertFalse(Files.exists(cache))
        }
        finally {
            Files.deleteIfExists(cache)
            Files.deleteIfExists(cache.parent)
        }
    }

    @Test
    fun `runtime lifecycle selects rolls back and removes verified installations`() {
        val root = Files.createTempDirectory("sage-runtime-lifecycle")
        try {
            val first = createInstalled(root, "10.6", "first")
            val second = createInstalled(root, "10.7", "second")
            Files.writeString(root.resolve("current"), first.name)
            val lifecycle = FileRuntimeLifecycle(root)

            assertEquals(first.runtimeId, lifecycle.current().value?.id)
            assertTrue(lifecycle.select(second.runtimeId).succeeded)
            assertEquals(second.runtimeId, lifecycle.current().value?.id)
            assertTrue(lifecycle.rollback().succeeded)
            assertEquals(first.runtimeId, lifecycle.current().value?.id)

            val removed = lifecycle.remove(first.runtimeId)
            assertTrue(removed.succeeded)
            assertEquals(second.runtimeId, lifecycle.current().value?.id)
            assertFalse(Files.exists(first.root))
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `corrupt current pointer exposes a diagnostic and rollback recovery`() {
        val root = Files.createTempDirectory("sage-runtime-current")
        try {
            val installed = createInstalled(root, "10.6", "only")
            Files.writeString(root.resolve("current"), "../escape")
            val lifecycle = FileRuntimeLifecycle(root)

            val inspection = lifecycle.current()
            assertFalse(inspection.succeeded)
            assertEquals(RuntimeDiagnosticCode.CURRENT_POINTER_CORRUPT, inspection.diagnostics.single().code)
            val recovered = lifecycle.rollback()
            assertTrue(recovered.succeeded)
            assertEquals(installed.runtimeId, recovered.value?.id)
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `settings and project SDK bindings resolve project override`() {
        val root = Files.createTempDirectory("sage-runtime-sdk")
        try {
            val settingsRuntime = createInstalled(root, "10.6", "settings")
            val projectRuntime = createInstalled(root, "10.7", "project")
            Files.writeString(root.resolve("current"), settingsRuntime.name)
            val adapter = RuntimeSdkAdapter(FileRuntimeLifecycle(root), InMemoryRuntimeSdkStore())
            val settingsTarget = RuntimeTarget.Native
            val projectTarget = RuntimeTarget.Wsl("Ubuntu-24.04")

            assertTrue(adapter.selectSettings(settingsRuntime.runtimeId, settingsTarget).succeeded)
            assertTrue(adapter.selectProject("project-a", projectRuntime.runtimeId, projectTarget).succeeded)
            assertEquals(projectRuntime.runtimeId, adapter.effective("project-a")?.runtimeId)
            assertEquals(projectTarget, adapter.effective("project-a")?.target)
            assertEquals(settingsRuntime.runtimeId, adapter.effective("project-b")?.runtimeId)
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `target aware probe keeps Native WSL Docker and SSH command boundaries`() {
        val requests = mutableListOf<TargetProcessRequest>()
        val executor = RuntimeTargetExecutor { request ->
            requests += request
            RuntimeProcessResult(RuntimeExecutionStatus.SUCCESS, 0, if (request.args.contains("--version")) "SageMath 10.6" else "4\n", "", 1, false)
        }
        val probe = TargetAwareRuntimeProbe(executor)

        val targets = listOf(
            RuntimeTarget.Native,
            RuntimeTarget.Wsl("Ubuntu-24.04"),
            RuntimeTarget.Docker("sage:10.6"),
            RuntimeTarget.RemoteSsh("sage.example.invalid", user = "ctf"),
        )
        targets.forEach { target ->
            val result = probe.probe(TargetRuntimeProbeRequest(target, "/opt/sage/sage"))
            assertEquals(RuntimeExecutionStatus.SUCCESS, result.status)
            assertEquals("4", result.expressionOutput)
        }

        assertEquals(8, requests.size)
        assertEquals(RuntimeTarget.Wsl("Ubuntu-24.04"), requests[2].target)
        assertTrue(requests[2].args.contains("--version"))
        assertEquals(RuntimeTarget.Docker("sage:10.6"), requests[4].target)
        assertEquals(RuntimeTarget.RemoteSsh("sage.example.invalid", user = "ctf"), requests[6].target)
    }

    @Test
    fun `non native target path mapping is explicit`() {
        val mapper = RuntimePathMapper()
        val local = Path.of("/workspace/project/input.sage")
        val mapping = RuntimePathMapping(Path.of("/workspace"), "/mnt/workspace")

        assertEquals("/mnt/workspace/project/input.sage", mapper.toTarget(local, RuntimeTarget.Wsl("Ubuntu", mapping)))
        assertEquals(local, mapper.toLocal("/mnt/workspace/project/input.sage", RuntimeTarget.Wsl("Ubuntu", mapping)))
        val error = kotlin.test.assertFailsWith<RuntimePathMappingException> {
            mapper.toTarget(local, RuntimeTarget.Docker("sage:latest"))
        }
        assertEquals(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, error.diagnostic.code)
    }

    private fun artifact(version: String, uri: String): RuntimeArtifact = RuntimeArtifact(
        SageRuntimeId(version, platform),
        URI(uri),
        ArchiveFormat.ZIP,
        sha256 = "0".repeat(64),
        entrypoint = "bin/sage",
    )

    private fun signed(document: RuntimeCatalogDocument): RuntimeCatalogEnvelope {
        val signer = java.security.Signature.getInstance("Ed25519")
        signer.initSign(privateKey())
        signer.update(RuntimeCatalogCodec.encode(document))
        return RuntimeCatalogEnvelope(
            document = document,
            keyId = "test-key",
            signature = signer.sign(),
        )
    }

    private fun testVerifier(): RuntimeCatalogSignatureVerifier = RuntimeCatalogSignatureVerifier(
        RuntimeCatalogTrustStore { keyId ->
            if (keyId == "test-key") {
                KeyFactory.getInstance("Ed25519").generatePublic(
                    java.security.spec.X509EncodedKeySpec(
                        "302a300506032b65700321004b74be146d1be2b867aaa07fa68a9132a860814834e8c17c20f32bf056311519"
                            .chunked(2).map { it.toInt(16).toByte() }.toByteArray(),
                    ),
                )
            }
            else null
        },
    )

    private fun privateKey(): PrivateKey {
        val bytes = seed.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
        return KeyFactory.getInstance("Ed25519").generatePrivate(
            EdECPrivateKeySpec(NamedParameterSpec.ED25519, bytes)
        )
    }

    private data class CreatedRuntime(
        val name: String,
        val root: Path,
        val runtimeId: SageRuntimeId,
    )

    private fun createInstalled(root: Path, version: String, label: String): CreatedRuntime {
        val id = SageRuntimeId(version, platform, distribution = label)
        val suffix = when (label) {
            "first" -> "00000000-0000-4000-8000-000000000001"
            "second" -> "00000000-0000-4000-8000-000000000002"
            "settings" -> "00000000-0000-4000-8000-000000000003"
            "project" -> "00000000-0000-4000-8000-000000000004"
            "only" -> "00000000-0000-4000-8000-000000000005"
            else -> error("Unknown test runtime label: $label")
        }
        val name = "${id.stableName()}-$suffix"
        val runtimeRoot = root.resolve("versions").resolve(name)
        Files.createDirectories(runtimeRoot.resolve("bin"))
        val executable = runtimeRoot.resolve("bin/sage")
        Files.writeString(executable, "sage-$label")
        val digest = Sha256ChecksumVerifier().sha256(executable)
        val manifest = RuntimeManifest(
            schemaVersion = 1,
            runtimeId = id,
            executable = "bin/sage",
            files = listOf(RuntimeFileRecord("bin/sage", Files.size(executable), digest)),
            artifactSha256 = "0".repeat(64),
        )
        Files.write(root.resolve("versions").resolve(".$name.meta"), RuntimeManifestCodec.encode(manifest))
        return CreatedRuntime(name, runtimeRoot, id)
    }

    private fun deleteTree(root: Path) {
        if (!Files.exists(root)) return
        Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
    }
}
