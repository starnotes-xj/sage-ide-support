package com.starnotesxj.sageide.run

import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.projectRoots.ProjectJdkTable
import com.intellij.openapi.projectRoots.Sdk
import com.intellij.openapi.ui.ComboBox
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.JBUI
import com.jetbrains.python.sdk.PythonSdkType
import com.jetbrains.python.run.PythonRunConfiguration
import com.starnotesxj.sageide.SageBundle
import com.starnotesxj.sageide.runtime.SageRuntimeSdkType
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import javax.swing.JComponent
import javax.swing.JLabel
import javax.swing.JPanel

/**
 * The editor shown in the Run/Debug Configurations dialog for Sage
 * configurations: script path and script parameters.
 */
class SageRunSettingsEditor : SettingsEditor<PythonRunConfiguration>() {

    private val scriptPathField = JBTextField()
    private val parametersField = JBTextField()
    private val sdkCombo = ComboBox<SdkChoice>()
    private val debuggerPythonSdkCombo = ComboBox<PythonSdkChoice>()

    override fun resetEditorFrom(configuration: PythonRunConfiguration) {
        val sageConfiguration = configuration as? SageRunConfiguration
            ?: throw IllegalArgumentException("SageRunSettingsEditor requires SageRunConfiguration")
        scriptPathField.text = sageConfiguration.scriptPath
        parametersField.text = sageConfiguration.sageScriptParameters
        rebuildSdkChoices()
        val selectedName = sageConfiguration.sageSdkName
        sdkCombo.selectedItem = sdkCombo.itemCount.takeIf { it > 0 }
            ?.let { (0 until it).map(sdkCombo::getItemAt).firstOrNull { choice -> choice.name == selectedName } }
            ?: sdkCombo.getItemAt(0)

        rebuildPythonSdkChoices()
        val selectedPythonSdk = if (sageConfiguration.isUseModuleSdk()) null else sageConfiguration.getSdk()
        debuggerPythonSdkCombo.selectedItem = (0 until debuggerPythonSdkCombo.itemCount)
            .map(debuggerPythonSdkCombo::getItemAt)
            .firstOrNull { it.sdk?.name == selectedPythonSdk?.name }
            ?: debuggerPythonSdkCombo.getItemAt(0)
    }

    override fun applyEditorTo(configuration: PythonRunConfiguration) {
        val sageConfiguration = configuration as? SageRunConfiguration
            ?: throw IllegalArgumentException("SageRunSettingsEditor requires SageRunConfiguration")
        sageConfiguration.scriptPath = scriptPathField.text
        sageConfiguration.sageScriptParameters = parametersField.text
        sageConfiguration.sageSdkName = (sdkCombo.selectedItem as? SdkChoice)?.name

        val pythonSdk = (debuggerPythonSdkCombo.selectedItem as? PythonSdkChoice)?.sdk
        if (pythonSdk == null) {
            sageConfiguration.setUseModuleSdk(true)
            sageConfiguration.setSdk(null)
            sageConfiguration.setSdkHome(null)
        } else {
            sageConfiguration.setUseModuleSdk(false)
            sageConfiguration.setSdk(pythonSdk)
            sageConfiguration.setSdkHome(pythonSdk.homePath)
        }
    }

    override fun createEditor(): JComponent {
        val panel = JPanel(GridBagLayout())
        val c = GridBagConstraints()
        c.fill = GridBagConstraints.HORIZONTAL
        c.anchor = GridBagConstraints.WEST
        c.insets = JBUI.insets(4, 4, 4, 4)

        fun row(y: Int, label: String, component: JComponent) {
            c.gridy = y
            c.gridx = 0
            c.weightx = 0.0
            panel.add(JLabel(label), c)
            c.gridx = 1
            c.weightx = 1.0
            panel.add(component, c)
        }

        row(0, SageBundle.message("run.editor.sdk"), sdkCombo)
        row(1, SageBundle.message("run.editor.debugger.python.sdk"), debuggerPythonSdkCombo)
        row(2, SageBundle.message("run.editor.script.path"), scriptPathField)
        row(3, SageBundle.message("run.editor.script.parameters"), parametersField)
        rebuildSdkChoices()
        rebuildPythonSdkChoices()
        return panel
    }

    private fun rebuildSdkChoices() {
        val selected = sdkCombo.selectedItem as? SdkChoice
        sdkCombo.removeAllItems()
        sdkCombo.addItem(SdkChoice(null, SageBundle.message("run.editor.global.runtime")))
        ProjectJdkTable.getInstance()
            .getSdksOfType(SageRuntimeSdkType.getInstance())
            .sortedBy { it.name }
            .forEach { sdkCombo.addItem(SdkChoice(it.name, it.name)) }
        selected?.name?.let { name ->
            sdkCombo.selectedItem = (0 until sdkCombo.itemCount)
                .map(sdkCombo::getItemAt)
                .firstOrNull { it.name == name }
                ?: sdkCombo.getItemAt(0)
        }
    }

    private fun rebuildPythonSdkChoices() {
        val selected = debuggerPythonSdkCombo.selectedItem as? PythonSdkChoice
        debuggerPythonSdkCombo.removeAllItems()
        debuggerPythonSdkCombo.addItem(PythonSdkChoice(null, SageBundle.message("run.editor.project.python.sdk")))
        ProjectJdkTable.getInstance().allJdks
            .filter { it.sdkType === PythonSdkType.getInstance() }
            .sortedBy { it.name }
            .forEach { debuggerPythonSdkCombo.addItem(PythonSdkChoice(it, it.name)) }
        selected?.sdk?.name?.let { name ->
            debuggerPythonSdkCombo.selectedItem = (0 until debuggerPythonSdkCombo.itemCount)
                .map(debuggerPythonSdkCombo::getItemAt)
                .firstOrNull { it.sdk?.name == name }
                ?: debuggerPythonSdkCombo.getItemAt(0)
        }
    }

    private data class SdkChoice(val name: String?, val label: String) {
        override fun toString(): String = label
    }

    private data class PythonSdkChoice(val sdk: Sdk?, val label: String) {
        override fun toString(): String = label
    }
}
