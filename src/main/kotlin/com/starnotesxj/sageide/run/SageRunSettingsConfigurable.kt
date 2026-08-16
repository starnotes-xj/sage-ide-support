package com.starnotesxj.sageide.run

import com.intellij.openapi.options.Configurable
import com.intellij.openapi.ui.ComboBox
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.JBUI
import java.awt.CardLayout
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import javax.swing.JButton
import javax.swing.JComponent
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.SwingUtilities

/**
 * Settings | Tools | SageMath: execution mode (Native / WSL / Docker) with
 * the per-mode settings, shared by every Sage run configuration.
 */
class SageRunSettingsConfigurable : Configurable {

    private val modeCombo = ComboBox(ExecutionMode.entries.toTypedArray())
    private val nativeCard = JPanel(GridBagLayout())
    private val wslCard = JPanel(GridBagLayout())
    private val dockerCard = JPanel(GridBagLayout())
    private val cards = JPanel(CardLayout())

    private val sageExecutableField = JBTextField()
    private val wslDistributionField = JBTextField()
    private val dockerImageField = JBTextField()
    private val dockerContainerDirField = JBTextField()
    private val dockerCommandField = JBTextField()
    private val sageParametersField = JBTextField()
    private val detectButton = JButton("Detect Sage installation")

    override fun getDisplayName(): String = "SageMath"

    override fun createComponent(): JComponent? {
        fun cardRow(panel: JPanel, y: Int, label: String, component: JComponent) {
            val c = GridBagConstraints()
            c.fill = GridBagConstraints.HORIZONTAL
            c.anchor = GridBagConstraints.WEST
            c.insets = JBUI.insets(4, 4, 4, 4)
            c.gridy = y
            c.gridx = 0
            c.weightx = 0.0
            panel.add(JLabel(label), c)
            c.gridx = 1
            c.weightx = 1.0
            panel.add(component, c)
        }

        cardRow(nativeCard, 0, "Sage executable:", sageExecutableField)
        cardRow(nativeCard, 1, "", detectButton)
        cardRow(nativeCard, 2, "Additional sage parameters:", sageParametersField)

        cardRow(wslCard, 0, "Sage executable (inside WSL):", sageExecutableField)
        cardRow(wslCard, 1, "WSL distribution:", wslDistributionField)
        cardRow(wslCard, 2, "Additional sage parameters:", sageParametersField)

        cardRow(dockerCard, 0, "Docker image:", dockerImageField)
        cardRow(dockerCard, 1, "Container mount directory:", dockerContainerDirField)
        cardRow(dockerCard, 2, "Command inside the container:", dockerCommandField)
        cardRow(dockerCard, 3, "Additional sage parameters:", sageParametersField)

        cards.layout = CardLayout()
        cards.add(nativeCard, ExecutionMode.NATIVE.name)
        cards.add(wslCard, ExecutionMode.WSL.name)
        cards.add(dockerCard, ExecutionMode.DOCKER.name)

        modeCombo.addActionListener {
            (cards.layout as CardLayout).show(cards, (modeCombo.selectedItem as ExecutionMode).name)
        }

        detectButton.addActionListener {
            detectButton.isEnabled = false
            Thread {
                val mode = modeCombo.selectedItem as ExecutionMode
                val result = when (mode) {
                    ExecutionMode.NATIVE -> SageAutoDetect.detectNativeSage()
                    ExecutionMode.WSL -> SageAutoDetect.detectWslSage(wslDistributionField.text)
                    ExecutionMode.DOCKER -> SageAutoDetect.detectDockerImage()
                }
                SwingUtilities.invokeLater {
                    if (result != null) {
                        when (mode) {
                            ExecutionMode.NATIVE, ExecutionMode.WSL -> sageExecutableField.text = result
                            ExecutionMode.DOCKER -> dockerImageField.text = result
                        }
                    }
                    detectButton.isEnabled = true
                }
            }.start()
        }

        val panel = JPanel(GridBagLayout())
        val c = GridBagConstraints()
        c.fill = GridBagConstraints.HORIZONTAL
        c.anchor = GridBagConstraints.WEST
        c.insets = JBUI.insets(4, 4, 4, 4)
        c.gridy = 0
        c.gridx = 0
        c.weightx = 0.0
        panel.add(JLabel("Execution mode:"), c)
        c.gridx = 1
        c.weightx = 1.0
        panel.add(modeCombo, c)
        c.gridy = 1
        c.gridx = 0
        c.gridwidth = 2
        c.weighty = 1.0
        panel.add(cards, c)
        return panel
    }

    override fun isModified(): Boolean {
        val s = SageRunSettings.getInstance().getState()
        return s.executionMode != (modeCombo.selectedItem as ExecutionMode).name ||
            s.sageExecutable != sageExecutableField.text ||
            s.sageParameters != sageParametersField.text ||
            s.wslDistribution != wslDistributionField.text ||
            s.dockerImage != dockerImageField.text ||
            s.dockerContainerDir != dockerContainerDirField.text ||
            s.dockerCommand != dockerCommandField.text
    }

    override fun apply() {
        val s = SageRunSettings.getInstance().getState()
        s.executionMode = (modeCombo.selectedItem as ExecutionMode).name
        s.sageExecutable = sageExecutableField.text
        s.sageParameters = sageParametersField.text
        s.wslDistribution = wslDistributionField.text
        s.dockerImage = dockerImageField.text
        s.dockerContainerDir = dockerContainerDirField.text
        s.dockerCommand = dockerCommandField.text
    }

    override fun reset() {
        val s = SageRunSettings.getInstance().getState()
        modeCombo.selectedItem = runCatching { ExecutionMode.valueOf(s.executionMode) }.getOrDefault(ExecutionMode.NATIVE)
        sageExecutableField.text = s.sageExecutable
        sageParametersField.text = s.sageParameters
        wslDistributionField.text = s.wslDistribution
        dockerImageField.text = s.dockerImage
        dockerContainerDirField.text = s.dockerContainerDir
        dockerCommandField.text = s.dockerCommand
        (cards.layout as CardLayout).show(cards, (modeCombo.selectedItem as ExecutionMode).name)
    }
}
