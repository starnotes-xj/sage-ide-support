package com.starnotesxj.sageide.run

import com.intellij.openapi.options.SettingsEditor
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.JBUI
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

    override fun resetEditorFrom(configuration: SageRunConfiguration) {
        scriptPathField.text = configuration.scriptPath
        parametersField.text = configuration.scriptParameters
    }

    override fun applyEditorTo(configuration: SageRunConfiguration) {
        configuration.scriptPath = scriptPathField.text
        configuration.scriptParameters = parametersField.text
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

        row(0, "Script path:", scriptPathField)
        row(1, "Script parameters:", parametersField)
        return panel
    }
}
