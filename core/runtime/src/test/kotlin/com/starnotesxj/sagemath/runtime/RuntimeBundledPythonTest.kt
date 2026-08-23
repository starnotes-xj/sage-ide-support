package com.starnotesxj.sagemath.runtime

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFilePermission
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class RuntimeBundledPythonTest {
    private val linux = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.X64, Libc.GLIBC)

    @Test
    fun `manifest round trips the explicit bundled Python path`() {
        val manifest = manifest(
            pythonExecutable = "local/bin/python3",
            files = listOf("sage", "local/bin/python3"),
        )

        val restored = RuntimeManifestCodec.decode(RuntimeManifestCodec.encode(manifest))

        assertEquals("local/bin/python3", restored.pythonExecutable)
        assertEquals(manifest, restored)
    }

    @Test
    fun `legacy manifest without Python metadata remains readable`() {
        val manifest = manifest(files = listOf("sage"))

        val restored = RuntimeManifestCodec.decode(RuntimeManifestCodec.encode(manifest))

        assertEquals(null, restored.pythonExecutable)
    }

    @Test
    fun `declared bundled Python must be listed in the manifest`() {
        kotlin.test.assertFailsWith<IllegalArgumentException> {
            manifest(pythonExecutable = "local/bin/python3", files = listOf("sage"))
        }
    }

    @Test
    fun `installed runtime resolves exactly the declared Python file`() {
        val root = Files.createTempDirectory("sage-bundled-python")
        try {
            val sage = root.resolve("sage")
            val python = root.resolve("local/bin/python3")
            Files.createDirectories(python.parent)
            Files.writeString(sage, "sage")
            Files.writeString(python, "python")
            makeExecutable(sage)
            makeExecutable(python)
            val manifest = manifest(
                pythonExecutable = "local/bin/python3",
                files = listOf("sage", "local/bin/python3"),
                bytes = mapOf("sage" to "sage", "local/bin/python3" to "python"),
            )
            val runtime = InstalledRuntime(SageRuntimeId("10.6", linux), root, sage, java.time.Instant.now(), manifest)

            assertEquals(python.toAbsolutePath().normalize(), runtime.pythonExecutable)
            assertEquals(python.toAbsolutePath().normalize().toString(), RuntimeExecutableResolver.resolve(runtime, RuntimeTarget.Native).value?.python)
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `target resolver maps bundled Python for WSL and requires remote root`() {
        val root = Files.createTempDirectory("sage-bundled-python-target")
        try {
            val sage = root.resolve("sage")
            val python = root.resolve("local/bin/python3")
            Files.createDirectories(python.parent)
            Files.writeString(sage, "sage")
            Files.writeString(python, "python")
            makeExecutable(sage)
            makeExecutable(python)
            val manifest = manifest(
                pythonExecutable = "local/bin/python3",
                files = listOf("sage", "local/bin/python3"),
                bytes = mapOf("sage" to "sage", "local/bin/python3" to "python"),
            )
            val runtime = InstalledRuntime(SageRuntimeId("10.6", linux), root, sage, java.time.Instant.now(), manifest)
            val wsl = RuntimeTarget.Wsl(
                "Ubuntu",
                pathMapping = RuntimePathMapping(root, "/opt/sage-runtime"),
            )

            val mapped = RuntimeExecutableResolver.resolve(runtime, wsl)
            assertTrue(mapped.succeeded)
            assertEquals("/opt/sage-runtime/local/bin/python3", mapped.value?.python)

            val remote = RuntimeExecutableResolver.resolve(runtime, RuntimeTarget.RemoteSsh("host"))
            assertFalse(remote.succeeded)
            assertEquals(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, remote.diagnostics.single().code)
            val remoteWithTargetRoot = RuntimeExecutableResolver.resolve(
                runtime,
                RuntimeTarget.RemoteSsh("host", runtimeRoot = "/opt/sage"),
            )
            assertEquals("/opt/sage/local/bin/python3", remoteWithTargetRoot.value?.python)
            val remoteWithRoot = RuntimeExecutableResolver.resolve(runtime, RuntimeTarget.RemoteSsh("host"), "/opt/sage")
            assertEquals("/opt/sage/local/bin/python3", remoteWithRoot.value?.python)
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `missing bundled Python fails closed without fallback`() {
        val root = Files.createTempDirectory("sage-bundled-python-missing")
        try {
            val sage = root.resolve("sage")
            Files.writeString(sage, "sage")
            makeExecutable(sage)
            val manifest = manifest(
                pythonExecutable = "local/bin/python3",
                files = listOf("sage", "local/bin/python3"),
                bytes = mapOf("sage" to "sage", "local/bin/python3" to "placeholder"),
            )
            val runtime = InstalledRuntime(SageRuntimeId("10.6", linux), root, sage, java.time.Instant.now(), manifest)

            assertFalse(RuntimeExecutableResolver.resolve(runtime, RuntimeTarget.Native).succeeded)
        }
        finally {
            deleteTree(root)
        }
    }

    private fun manifest(
        pythonExecutable: String? = null,
        files: List<String>,
        bytes: Map<String, String> = files.associateWith { it },
    ): RuntimeManifest {
        val records = files.map { path ->
            val content = bytes[path] ?: "placeholder"
            RuntimeFileRecord(path, content.toByteArray().size.toLong(), digestOf(content.toByteArray()))
        }
        return RuntimeManifest(
            schemaVersion = 1,
            runtimeId = SageRuntimeId("10.6", linux),
            executable = "sage",
            files = records,
            artifactSha256 = "0".repeat(64),
            pythonExecutable = pythonExecutable,
        )
    }

    private fun makeExecutable(path: Path) {
        if (Files.getFileAttributeView(path, java.nio.file.attribute.PosixFileAttributeView::class.java) != null) {
            Files.setPosixFilePermissions(path, setOf(PosixFilePermission.OWNER_READ, PosixFilePermission.OWNER_EXECUTE))
        }
    }

    private fun digestOf(bytes: ByteArray): String =
        java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    private fun deleteTree(root: Path) {
        Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
    }
}
