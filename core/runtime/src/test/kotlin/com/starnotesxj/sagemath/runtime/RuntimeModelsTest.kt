package com.starnotesxj.sagemath.runtime

import java.net.URI
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNotEquals

class RuntimeModelsTest {
    private val platform = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.X64, Libc.GLIBC)

    @Test
    fun `platform detector normalizes common host values`() {
        assertEquals(
            PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64),
            PlatformDetector.detect("Windows 11", "amd64"),
        )
        assertEquals(
            PlatformTriple(OperatingSystem.MACOS, CpuArchitecture.ARM64),
            PlatformDetector.detect("Mac OS X", "aarch64"),
        )
    }

    @Test
    fun `artifact requires https and strict digest`() {
        assertFailsWith<IllegalArgumentException> {
            RuntimeArtifact(
                SageRuntimeId("10.6", platform),
                URI("http://example.invalid/sage.zip"),
                ArchiveFormat.ZIP,
                sha256 = "0".repeat(64),
            )
        }
        assertFailsWith<IllegalArgumentException> {
            RuntimeArtifact(
                SageRuntimeId("10.6", platform),
                URI("https://example.invalid/sage.zip"),
                ArchiveFormat.ZIP,
                sha256 = "bad",
            )
        }
    }

    @Test
    fun `unsafe relative paths are rejected`() {
        assertFailsWith<IllegalArgumentException> {
            RuntimeArtifact(
                SageRuntimeId("10.6", platform),
                URI("https://example.invalid/sage.zip"),
                ArchiveFormat.ZIP,
                sha256 = "0".repeat(64),
                entrypoint = "../sage",
            )
        }
    }

    @Test
    fun `stable runtime name does not collide after sanitization`() {
        val first = SageRuntimeId("10/6", platform, distribution = "managed")
        val second = SageRuntimeId("10_6", platform, distribution = "managed")

        assertNotEquals(first.stableName(), second.stableName())
    }

    @Test
    fun `windows reserved and control paths are rejected`() {
        assertFailsWith<IllegalArgumentException> {
            RuntimeArtifact(
                SageRuntimeId("10.6", platform),
                URI("https://example.invalid/sage.zip"),
                ArchiveFormat.ZIP,
                sha256 = "0".repeat(64),
                entrypoint = "CON",
            )
        }
        assertFailsWith<IllegalArgumentException> {
            RuntimeArtifact(
                SageRuntimeId("10.6", platform),
                URI("https://example.invalid/sage.zip"),
                ArchiveFormat.ZIP,
                sha256 = "0".repeat(64),
                entrypoint = "bin/sage\u0000.exe",
            )
        }
    }

    @Test
    fun `non NFC paths are rejected`() {
        assertFailsWith<IllegalArgumentException> {
            RuntimeFileRecord("cafe\u0301", 1, "0".repeat(64))
        }
    }

    @Test
    fun `manifest rejects a mismatched SageMath version`() {
        assertFailsWith<IllegalArgumentException> {
            RuntimeManifest(
                schemaVersion = 1,
                runtimeId = SageRuntimeId("10.6", platform),
                executable = "sage",
                files = listOf(RuntimeFileRecord("sage", 1, "0".repeat(64))),
                artifactSha256 = "0".repeat(64),
                sageVersion = "10.5",
            )
        }
    }

    @Test
    fun `manifest codec round trips complete manifest`() {
        val id = SageRuntimeId("10.6", platform)
        val manifest = RuntimeManifest(
            schemaVersion = 1,
            runtimeId = id,
            executable = "bin/sage",
            files = listOf(RuntimeFileRecord("bin/sage", 4, "0".repeat(64))),
            artifactSha256 = "1".repeat(64),
            pythonVersion = "3.13",
        )

        assertEquals(manifest, RuntimeManifestCodec.decode(RuntimeManifestCodec.encode(manifest)))
    }

    @Test
    fun `static catalog filters by runtime query`() {
        val artifact = RuntimeArtifact(
            SageRuntimeId("10.6", platform),
            URI("https://example.invalid/sage.zip"),
            ArchiveFormat.ZIP,
            sha256 = "0".repeat(64),
        )
        val catalog = StaticRuntimeCatalog(listOf(artifact))

        assertEquals(listOf(artifact), catalog.list(RuntimeQuery(version = "10.6", platform = platform)))
        assertEquals(emptyList(), catalog.list(RuntimeQuery(version = "10.5", platform = platform)))
    }
}
