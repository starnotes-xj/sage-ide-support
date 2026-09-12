package com.starnotesxj.sageide.run

import com.intellij.openapi.options.SettingsEditor
import com.intellij.openapi.projectRoots.ProjectJdkTable
import com.intellij.openapi.projectRoots.Sdk
import com.intellij.openapi.ui.ComboBox
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.JBUI
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
class SageRunSettingsEditor : SettingsEditor<SageRunConfiguration>() {

    private val scriptPathField = JBTextField()
    private val parametersField = JBTextField()
    private val sdkCombo = ComboBox<SdkChoice>()

    override fun resetEditorFrom(configuration: SageRunConfiguration) {
        scriptPathField.text = configuration.scriptPath
        parametersField.text = configuration.scriptParameters
        rebuildSdkChoices()
        val selectedName = configuration.sageSdkName
        sdkCombo.selectedItem = sdkCombo.itemCount.takeIf { it > 0 }
            ?.let { (0 until it).map(sdkCombo::getItemAt).firstOrNull { choice -> choice.name == selectedName } }
            ?: sdkCombo.getItemAt(0)
    }

    override fun applyEditorTo(configuration: SageRunConfiguration) {
        configuration.scriptPath = scriptPathField.text
        configuration.scriptParameters = parametersField.text
        configuration.sageSdkName = (sdkCombo.selectedItem as? SdkChoice)?.name
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
        row(1, SageBundle.message("run.editor.script.path"), scriptPathField)
        row(2, SageBundle.message("run.editor.script.parameters"), parametersField)
        rebuildSdkChoices()
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

    private data class SdkChoice(val name: String?, val label: String) {
        override fun toString(): String = label
    }
}
