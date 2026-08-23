package com.starnotesxj.sageide.runtime

import com.starnotesxj.sagemath.runtime.CpuArchitecture
import com.starnotesxj.sagemath.runtime.OperatingSystem
import com.starnotesxj.sagemath.runtime.PlatformTriple
import com.starnotesxj.sagemath.runtime.RuntimeDiagnostic
import com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import com.starnotesxj.sagemath.runtime.SageRuntimeId
import org.jdom.Element
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class SageRuntimeSdkDataTest {
    private val id = SageRuntimeId(
        "10.6",
        PlatformTriple(OperatingSystem.LINUX, CpuArchitecture.X64),
        distribution = "managed",
    )

    @Test
    fun `additional data round trips target identity without credentials`() {
        val data = SageRuntimeSdkAdditionalData(
            id,
            RuntimeTarget.RemoteSsh("sage.example.invalid", user = "ctf", port = 2201, runtimeRoot = "/opt/sage-runtime"),
        )
        val element = Element("additional")

        data.save(element)
        val restored = SageRuntimeSdkAdditionalData.load(element)

        assertNotNull(restored)
        assertEquals(data.runtimeId, restored!!.runtimeId)
        assertEquals(data.target, restored.target)
        assertEquals("ssh", element.getAttributeValue("targetKind"))
        assertEquals("sage.example.invalid", element.getAttributeValue("targetHost"))
        assertEquals("/opt/sage-runtime", element.getAttributeValue("targetRuntimeRoot"))
        assertNull(element.getAttributeValue("privateKey"))
        assertNull(element.getAttributeValue("password"))
        assertNull(element.getAttributeValue("token"))
        assertNull(element.getAttributeValue("pythonExecutable"))
        assertNull(element.getAttributeValue("pythonSdkName"))
    }

    @Test
    fun `service facade exposes one canonical lifecycle instance`() {
        val service = SageRuntimeManagerService()
        assertEquals(service.installRoot, service.installRoot.toAbsolutePath().normalize())
        assertTrue(service.installRoot.toString().replace('\\', '/').endsWith("/.sage-math-ctf-ide/runtimes"))
        service.dispose()
    }

    @Test
    fun `presentation distinguishes target mismatch missing and invalid`() {
        val binding = SageRuntimeSdkAdditionalData(id, RuntimeTarget.Native).binding()

        assertEquals(
            SageRuntimeSdkState.TARGET_MISMATCH,
            presentationFor("sdk", binding, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_MISMATCH, "test", "mismatch"))).state,
        )
        assertEquals(
            SageRuntimeSdkState.MISSING,
            presentationFor("sdk", binding, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED, "test", "missing"))).state,
        )
        assertEquals(
            SageRuntimeSdkState.INVALID,
            presentationFor("sdk", binding, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_INVALID, "test", "invalid"))).state,
        )
    }

    @Test
    fun `display labels include runtime and target but not unstable object identity`() {
        val binding = SageRuntimeSdkAdditionalData(id, RuntimeTarget.Wsl("Ubuntu")).binding()
        val label = SageRuntimeSdkDisplay.sdkName(binding)

        assertTrue(label.contains("10.6"))
        assertTrue(label.contains("linux-x64"))
        assertTrue(label.contains("WSL: Ubuntu"))
        assertTrue(SageRuntimeSdkDisplay.targetLabel(RuntimeTarget.RemoteSsh("host", runtimeRoot = "/opt/sage")).contains("/opt/sage"))
        assertTrue(!label.contains("RuntimeTarget.Wsl"))
    }
}
