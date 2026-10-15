package com.starnotesxj.sageide.run

import com.starnotesxj.sageide.PythonSdkPluginTestBase
import kotlin.test.assertFalse
import kotlin.test.assertSame
import kotlin.test.assertTrue

class SageRunSettingsEditorTest : PythonSdkPluginTestBase() {

    fun testProjectModulePythonSdkRemainsTheDefault() {
        val configuration = newConfiguration().apply { setUseModuleSdk(true) }
        val editor = SageRunSettingsEditor()

        editor.resetFrom(configuration)
        editor.applyTo(configuration)

        assertTrue(configuration.isUseModuleSdk())
        assertSame(testSdk, configuration.getSdk())
    }

    fun testExplicitDebuggerPythonSdkIsSavedOnTheConfiguration() {
        val configuration = newConfiguration().apply { setUseModuleSdk(true) }
        val editor = SageRunSettingsEditor()
        editor.resetFrom(configuration)

        val comboField = SageRunSettingsEditor::class.java.getDeclaredField("debuggerPythonSdkCombo")
            .apply { isAccessible = true }
        @Suppress("UNCHECKED_CAST")
        val combo = comboField.get(editor) as com.intellij.openapi.ui.ComboBox<Any>
        val testSdkName = requireNotNull(testSdk).name
        val selectedIndex = (0 until combo.itemCount).first { combo.getItemAt(it).toString() == testSdkName }
        combo.selectedIndex = selectedIndex

        editor.applyTo(configuration)

        assertFalse(configuration.isUseModuleSdk())
        assertSame(testSdk, configuration.getSdk())
    }

    private fun newConfiguration(): SageRunConfiguration = SageRunConfiguration(
        myFixture.project,
        SageConfigurationFactory(SageRunConfigurationType()),
    )
}
