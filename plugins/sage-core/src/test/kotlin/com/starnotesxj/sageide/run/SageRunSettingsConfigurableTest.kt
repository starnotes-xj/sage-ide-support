package com.starnotesxj.sageide.run

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertSame
import kotlin.test.assertTrue
import kotlin.test.assertFailsWith
import java.util.Locale
import java.util.ResourceBundle

class SageRunSettingsConfigurableTest {
    @Test
    fun `live Sage type evidence defaults on and upgrades legacy settings once`() {
        assertTrue(SageRunSettings.State().liveTypeProbingEnabled)

        val legacy = SageRunSettings.State().apply {
            liveTypeProbingEnabled = false
            liveTypeProbingConfigured = false
        }
        SageRunSettings().loadState(legacy)

        assertTrue(legacy.liveTypeProbingEnabled)
        assertTrue(legacy.liveTypeProbingConfigured)
    }

    @Test
    fun `Chinese bundle follows the IDE locale resource convention`() {
        val messages = ResourceBundle.getBundle("messages.SageBundle", Locale.SIMPLIFIED_CHINESE)

        assertEquals("运行 Sage 脚本", messages.getString("run.action.run"))
        assertEquals("启用 Sage 实时类型证据（隔离快照与正常运行回传）", messages.getString("settings.live.type.evidence"))
    }

    @Test
    fun `settings state keeps native WSL SSH and legacy executable independent`() {
        val state = SageRunSettings.State().apply {
            sageExecutable = "C:/legacy/sage.exe"
        }
        SageRunSettings().loadState(state)
        assertEquals("C:/legacy/sage.exe", state.nativeSageExecutable)
        assertEquals("", state.wslSageExecutable)

        state.nativeSageExecutable = "C:/Sage/sage.exe"
        state.wslSageExecutable = "/home/user/miniconda3/envs/sage/bin/sage"
        state.sshSageExecutable = "/opt/sage-runtime/bin/sage"
        assertEquals("C:/Sage/sage.exe", state.nativeSageExecutable)
        assertEquals("/home/user/miniconda3/envs/sage/bin/sage", state.wslSageExecutable)
        assertEquals("/opt/sage-runtime/bin/sage", state.sshSageExecutable)
    }

    @Test
    fun `configurable component is idempotent and shared parameters have one parent`() {
        val configurable = SageRunSettingsConfigurable()
        val first = configurable.createComponent()
        val second = configurable.createComponent()
        assertNotNull(first)
        assertSame(first, second)
        assertTrue(first!!.components.size >= 4)
        configurable.disposeUIResources()
        val recreated = configurable.createComponent()
        assertNotNull(recreated)
        assertFalse(recreated === first)
        configurable.disposeUIResources()
    }

    @Test
    fun `apply rejects malformed SSH numeric fields without persisting`() {
        val settings = SageRunSettings.State().apply {
            executionMode = ExecutionMode.NATIVE.name
            sshPort = 2222
            sshConnectTimeoutSeconds = 20
        }
        SageRunSettings().loadState(settings)
        val configurable = SageRunSettingsConfigurable()
        configurable.createComponent()
        val portField = configurable.javaClass.getDeclaredField("sshPortField").apply { isAccessible = true }.get(configurable) as javax.swing.JTextField
        val timeoutField = configurable.javaClass.getDeclaredField("sshTimeoutField").apply { isAccessible = true }.get(configurable) as javax.swing.JTextField
        portField.text = "abc"
        timeoutField.text = "0"
        assertFailsWith<com.intellij.openapi.options.ConfigurationException> { configurable.apply() }
        assertEquals(2222, settings.sshPort)
        assertEquals(20, settings.sshConnectTimeoutSeconds)
        configurable.disposeUIResources()
    }

    @Test
    fun `SSH settings round trip through state`() {
        val state = SageRunSettings.State().apply {
            executionMode = ExecutionMode.SSH.name
            sshHost = "sage.example"
            sshUser = "ctf"
            sshPort = 2201
            sshKnownHostsFile = "G:/ssh/known_hosts"
            sshAuthentication = "IDENTITY_FILE"
            sshIdentityFile = "G:/ssh/id_ed25519"
            sshRuntimeRoot = "/opt/sage-runtime"
            sshSageExecutable = "/opt/sage-runtime/bin/sage"
            sshLocalRoot = "G:/workspace"
            sshTargetRoot = "/srv/workspace"
            sshConnectTimeoutSeconds = 15
        }
        assertEquals(ExecutionMode.SSH.name, state.executionMode)
        assertEquals(2201, state.sshPort)
        assertEquals("IDENTITY_FILE", state.sshAuthentication)
        assertTrue(state.sshRuntimeRoot.startsWith("/"))
    }
}
