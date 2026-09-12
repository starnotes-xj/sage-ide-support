package com.starnotesxj.sagemath.runtime

import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.attribute.PosixFileAttributeView
import java.nio.file.attribute.PosixFilePermission
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNull
import kotlin.test.assertTrue

class RuntimeSdkAdapterTest {
    private val linux = PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.X64, Libc.GLIBC)

    @Test
    fun `missing runtime is rejected without changing settings`() {
        val root = Files.createTempDirectory("sage-sdk-missing")
        try {
            val store = InMemoryRuntimeSdkStore()
            val adapter = RuntimeSdkAdapter(FileRuntimeLifecycle(root), store)
            val id = SageRuntimeId("10.6", linux)

            val result = adapter.selectSettings(id, RuntimeTarget.Native)

            assertFalse(result.succeeded)
            assertEquals(RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED, result.diagnostics.single().code)
            assertNull(store.settings())
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `target platform mismatch is rejected before selection`() {
        val root = Files.createTempDirectory("sage-sdk-target-mismatch")
        try {
            val runtime = createInstalled(root, SageRuntimeId("10.6", linux), "mismatch")
            Files.writeString(root.resolve("current"), runtime.name)
            val adapter = RuntimeSdkAdapter(FileRuntimeLifecycle(root), InMemoryRuntimeSdkStore())

            val result = adapter.selectSettings(
                runtime.id,
                RuntimeTarget.Wsl(
                    "Ubuntu",
                    targetPlatform = PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64),
                ),
            )

            assertFalse(result.succeeded)
            assertEquals(RuntimeDiagnosticCode.TARGET_MISMATCH, result.diagnostics.single().code)
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `invalid runtime selection and effective binding are not published`() {
        val root = Files.createTempDirectory("sage-sdk-invalid")
        try {
            val id = SageRuntimeId("10.6", linux)
            val runtime = createInstalled(root, id, "invalid")
            Files.writeString(root.resolve("current"), runtime.name)
            Files.writeString(runtime.root.resolve("bin/sage"), "tampered")
            val store = InMemoryRuntimeSdkStore()
            val adapter = RuntimeSdkAdapter(FileRuntimeLifecycle(root), store)

            val selection = adapter.selectSettings(id, RuntimeTarget.Native)
            val effective = adapter.effectiveResult("project-a")

            assertFalse(selection.succeeded)
            assertEquals(RuntimeDiagnosticCode.RUNTIME_INVALID, selection.diagnostics.single().code)
            assertFalse(effective.succeeded)
            assertEquals(RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED, effective.diagnostics.single().code)
            assertNull(store.settings())
        }
        finally {
            deleteTree(root)
        }
    }

    @Test
    fun `project override target mismatch does not hide valid settings fallback`() {
        val root = Files.createTempDirectory("sage-sdk-override")
        try {
            val settings = createInstalled(root, SageRuntimeId("10.6", linux), "settings")
            val project = createInstalled(root, SageRuntimeId("10.7", linux), "project")
            Files.writeString(root.resolve("current"), settings.name)
            val store = InMemoryRuntimeSdkStore()
            val adapter = RuntimeSdkAdapter(FileRuntimeLifecycle(root), store)
            assertTrue(adapter.selectSettings(settings.id, RuntimeTarget.Native).succeeded)
            store.setProject("project-a", RuntimeSdkBinding(project.id, RuntimeTarget.Wsl("Ubuntu", targetPlatform = PlatformTriple(OperatingSystem.WINDOWS, CpuArchitecture.X64))))

            val effective = adapter.effectiveResult("project-a")

            assertFalse(effective.succeeded)
            assertEquals(RuntimeDiagnosticCode.TARGET_MISMATCH, effective.diagnostics.single().code)
            assertEquals(settings.id, adapter.effective("project-b")?.runtimeId)
        }
        finally {
            deleteTree(root)
        }
    }

    private data class CreatedRuntime(val name: String, val root: Path, val id: SageRuntimeId)

    private fun createInstalled(root: Path, id: SageRuntimeId, label: String): CreatedRuntime {
        val suffix = when (label) {
            "mismatch" -> "00000000-0000-4000-8000-000000000001"
            "invalid" -> "00000000-0000-4000-8000-000000000002"
            "settings" -> "00000000-0000-4000-8000-000000000003"
            "project" -> "00000000-0000-4000-8000-000000000004"
            else -> error("Unknown test runtime label: $label")
        }
        val name = "${id.stableName()}-$suffix"
        val runtimeRoot = root.resolve("versions").resolve(name)
        Files.createDirectories(runtimeRoot.resolve("bin"))
        val executable = runtimeRoot.resolve("bin/sage")
        Files.writeString(executable, "sage-$label")
        markExecutableWhenSupported(executable)
        val manifest = RuntimeManifest(
            schemaVersion = 1,
            runtimeId = id,
            executable = "bin/sage",
            files = listOf(RuntimeFileRecord("bin/sage", Files.size(executable), Sha256ChecksumVerifier().sha256(executable))),
            artifactSha256 = "0".repeat(64),
        )
        Files.write(root.resolve("versions").resolve(".$name.meta"), RuntimeManifestCodec.encode(manifest))
        return CreatedRuntime(name, runtimeRoot, id)
    }

    private fun markExecutableWhenSupported(path: Path) {
        if (Files.getFileAttributeView(path, PosixFileAttributeView::class.java) != null) {
            Files.setPosixFilePermissions(path, Files.getPosixFilePermissions(path) + PosixFilePermission.OWNER_EXECUTE)
        }
    }

    private fun deleteTree(root: Path) {
        if (!Files.exists(root)) return
        Files.walk(root).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
    }
}
