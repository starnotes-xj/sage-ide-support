package com.starnotesxj.sagemath.runtime

import java.net.URI
import java.nio.file.Files
import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue
import kotlin.test.assertNotNull

class RuntimeManifestVerifierTest {
    @Test
    fun `manifest verification checks size digest and unexpected files`() {
        val root = Files.createTempDirectory("sage-runtime-manifest")
        try {
            val executable = root.resolve("sage")
            Files.writeString(executable, "sage launcher")
            if (Files.getFileAttributeView(executable, java.nio.file.attribute.PosixFileAttributeView::class.java) != null) {
                Files.setPosixFilePermissions(
                    executable,
                    setOf(
                        java.nio.file.attribute.PosixFilePermission.OWNER_READ,
                        java.nio.file.attribute.PosixFilePermission.OWNER_WRITE,
                        java.nio.file.attribute.PosixFilePermission.OWNER_EXECUTE,
                    ),
                )
            }
            val digest = Sha256ChecksumVerifier().sha256(executable)
            val platform = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.X64, Libc.GLIBC)
            val id = SageRuntimeId("10.6", platform)
            val manifest = RuntimeManifest(
                schemaVersion = 1,
                runtimeId = id,
                executable = "sage",
                files = listOf(RuntimeFileRecord("sage", Files.size(executable), digest)),
                artifactSha256 = "0".repeat(64),
            )
            val verifier = FileRuntimeManifestVerifier()

            assertTrue(verifier.verify(root, manifest).valid)
            Files.writeString(root.resolve("unexpected"), "not in manifest")
            assertFalse(verifier.verify(root, manifest).valid)
            Files.delete(root.resolve("unexpected"))
            Files.write(root.resolve("special"), byteArrayOf(1))
            assertFalse(verifier.verify(root, manifest).valid)
        }
        finally {
            Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `file runtime locator follows verified current pointer`() {
        val root = Files.createTempDirectory("sage-runtime-locator")
        try {
            val platform = PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64)
            val id = SageRuntimeId("10.6", platform)
            val versionName = "managed-10.6-windows-x64"
            val versionRoot = root.resolve("versions").resolve(versionName)
            Files.createDirectories(versionRoot)
            val executable = versionRoot.resolve("sage.exe")
            Files.writeString(executable, "sage")
            val manifest = RuntimeManifest(
                schemaVersion = 1,
                runtimeId = id,
                executable = "sage.exe",
                files = listOf(RuntimeFileRecord("sage.exe", 4, digestOf("sage".toByteArray()))),
                artifactSha256 = "0".repeat(64),
            )
            Files.write(root.resolve("versions").resolve(".$versionName.meta"), RuntimeManifestCodec.encode(manifest))
            Files.writeString(root.resolve("current"), versionName)

            val located = FileRuntimeLocator().locate(root, id)

            assertNotNull(located)
            assertTrue(located.executable.endsWith("sage.exe"))
        }
        finally {
            Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        }
    }

    @Test
    fun `manifest schema and artifact identity must agree`() {
        val platform = PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64)
        val id = SageRuntimeId("10.6", platform)
        val artifact = RuntimeArtifact(
            id,
            URI("https://example.invalid/runtime.zip"),
            ArchiveFormat.ZIP,
            sha256 = "0".repeat(64),
            entrypoint = "sage.exe",
        )
        val otherId = SageRuntimeId("10.5", platform)
        val manifest = RuntimeManifest(
            schemaVersion = 1,
            runtimeId = otherId,
            executable = "sage.exe",
            files = listOf(RuntimeFileRecord("sage.exe", 0, "0".repeat(64))),
            artifactSha256 = "0".repeat(64),
        )

        kotlin.test.assertFailsWith<IllegalArgumentException> {
            RuntimeInstallRequest(artifact, Files.createTempDirectory("runtime-request"), manifest = manifest)
        }
    }

    private fun digestOf(bytes: ByteArray): String {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        return digest.digest(bytes).joinToString("") { "%02x".format(it) }
    }
}
