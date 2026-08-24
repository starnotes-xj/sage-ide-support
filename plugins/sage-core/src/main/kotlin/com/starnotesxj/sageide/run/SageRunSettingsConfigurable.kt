package com.starnotesxj.sageide.run

import com.intellij.openapi.options.Configurable
import com.intellij.openapi.options.ConfigurationException
import com.intellij.openapi.ui.ComboBox
import com.intellij.ui.components.JBTextField
import com.starnotesxj.sagemath.runtime.RuntimeDiagnostic
import com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode
import com.starnotesxj.sagemath.runtime.RuntimeOperationResult
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

    private val nativeSageExecutableField = JBTextField()
    private val wslSageExecutableField = JBTextField()
    private val wslDistributionField = JBTextField()
    private val wslCondaEnvironmentField = JBTextField()
    private val wslCondaExecutableField = JBTextField()
    private val containerExecutableField = JBTextField()
    private val dockerImageField = JBTextField()
    private val dockerContainerDirField = JBTextField()
    private val dockerCommandField = JBTextField()
    private val sageParametersField = JBTextField()
    private val sshCard = JPanel(GridBagLayout())
    private val sshHostField = JBTextField()
    private val sshUserField = JBTextField()
    private val sshPortField = JBTextField()
    private val sshKnownHostsField = JBTextField()
    private val sshAuthenticationField = JBTextField("AGENT")
    private val sshIdentityField = JBTextField()
    private val sshRuntimeRootField = JBTextField()
    private val sshSageExecutableField = JBTextField()
    private val sshLocalRootField = JBTextField()
    private val sshTargetRootField = JBTextField()
    private val sshTimeoutField = JBTextField("10")
    private val detectButton = JButton("Detect Sage installation")
    private val statusLabel = JLabel()
    private var rootComponent: JComponent? = null
    private var detectRequest = 0L
    private var activeProbe: SageRuntimeProbeHandle<*>? = null

    override fun getDisplayName(): String = "SageMath"

    override fun createComponent(): JComponent? {
        rootComponent?.let { return it }
        listOf(nativeCard, wslCard, dockerCard, sshCard).forEach { it.removeAll() }
        cards.removeAll()
        modeCombo.actionListeners.toList().forEach(modeCombo::removeActionListener)
        detectButton.actionListeners.toList().forEach(detectButton::removeActionListener)
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

        cardRow(nativeCard, 0, "Sage executable:", nativeSageExecutableField)

        cardRow(wslCard, 0, "Sage executable (inside WSL):", wslSageExecutableField)
        cardRow(wslCard, 1, "WSL distribution:", wslDistributionField)
        cardRow(wslCard, 2, "Conda environment:", wslCondaEnvironmentField)
        cardRow(wslCard, 3, "Conda executable (optional):", wslCondaExecutableField)

        cardRow(dockerCard, 0, "Container executable (docker/podman):", containerExecutableField)
        cardRow(dockerCard, 1, "Container image:", dockerImageField)
        cardRow(dockerCard, 2, "Container mount directory:", dockerContainerDirField)
        cardRow(dockerCard, 3, "Command inside the container:", dockerCommandField)

        cardRow(sshCard, 0, "SSH host:", sshHostField)
        cardRow(sshCard, 1, "SSH user (optional):", sshUserField)
        cardRow(sshCard, 2, "SSH port:", sshPortField)
        cardRow(sshCard, 3, "Known hosts file:", sshKnownHostsField)
        cardRow(sshCard, 4, "Authentication (AGENT/IDENTITY_FILE):", sshAuthenticationField)
        cardRow(sshCard, 5, "Identity file (for IDENTITY_FILE):", sshIdentityField)
        cardRow(sshCard, 6, "Remote runtime root:", sshRuntimeRootField)
        cardRow(sshCard, 7, "Remote Sage executable:", sshSageExecutableField)
        cardRow(sshCard, 8, "Local mapping root:", sshLocalRootField)
        cardRow(sshCard, 9, "Remote mapping root:", sshTargetRootField)
        cardRow(sshCard, 10, "Connect timeout (seconds):", sshTimeoutField)

        cards.layout = CardLayout()
        cards.add(nativeCard, ExecutionMode.NATIVE.name)
        cards.add(wslCard, ExecutionMode.WSL.name)
        cards.add(dockerCard, ExecutionMode.DOCKER.name)
        cards.add(sshCard, ExecutionMode.SSH.name)

        modeCombo.addActionListener {
            invalidateDetection()
            (cards.layout as CardLayout).show(cards, (modeCombo.selectedItem as ExecutionMode).name)
        }

        detectButton.addActionListener {
            val request = ++detectRequest
            val mode = modeCombo.selectedItem as ExecutionMode
            val nativeConfigured = nativeSageExecutableField.text
            val wslDistribution = wslDistributionField.text
            val wslEnvironment = wslCondaEnvironmentField.text
            val wslConda = wslCondaExecutableField.text
            val wslSage = wslSageExecutableField.text
            val containerEngine = containerExecutableField.text
            val containerImage = dockerImageField.text
            val containerCommand = dockerCommandField.text
            detectButton.isEnabled = false
            statusLabel.text = "Detecting…"
            activeProbe?.cancel()
            activeProbe = null
            val service = SageRuntimeService.getInstance()
            activeProbe = when (mode) {
                ExecutionMode.NATIVE -> service.submit { control ->
                    val executable = service.resolveNativeExecutable(nativeConfigured)
                    executable to (executable?.let { service.probeConfiguredNative(it, control) })
                }
                ExecutionMode.WSL -> service.submit { control ->
                    control.status()
                    SageAutoDetect.detectWslRuntime(wslDistribution, wslEnvironment, wslConda, wslSage, timeoutMillis = 10_000)
                }
                ExecutionMode.DOCKER -> service.submit { control ->
                    val image = containerImage.ifBlank { SageAutoDetect.detectDockerImage() }
                    image?.let {
                        val state = SageRunSettings.State().apply {
                            containerExecutable = containerEngine
                            dockerImage = it
                            dockerContainerDir = dockerContainerDirField.text
                            dockerCommand = containerCommand
                        }
                        service.resolveContainerExecutables(state, control = control)
                    }
                }
                ExecutionMode.SSH -> service.submit { _ -> "SSH" }
            }
            val future = activeProbe!!.future
            future.whenComplete { value, error ->
                SwingUtilities.invokeLater {
                    if (request != detectRequest || rootComponent == null || mode != modeCombo.selectedItem) return@invokeLater
                    activeProbe = null
                    detectButton.isEnabled = true
                    when (mode) {
                        ExecutionMode.NATIVE -> {
                            val pair = value as? Pair<*, *>
                            val executable = pair?.first as? String
                            val probe = pair?.second as? com.starnotesxj.sagemath.runtime.RuntimeProbeResult
                            if (error == null && probe?.status == com.starnotesxj.sagemath.runtime.RuntimeExecutionStatus.SUCCESS && executable != null) {
                                nativeSageExecutableField.text = executable
                                statusLabel.text = "Validated native Sage"
                            } else {
                                statusLabel.text = "Native Sage probe failed: ${probe?.status ?: error?.message ?: "unknown"}"
                            }
                        }
                        ExecutionMode.WSL -> {
                            val result = value as? WslSageRuntime
                            if (error == null && result != null) {
                                wslSageExecutableField.text = result.sageExecutable
                                wslCondaExecutableField.text = result.condaExecutable.orEmpty()
                                statusLabel.text = "Validated WSL Sage ${result.version ?: "runtime"} · ${result.pythonExecutable ?: "Python unavailable"}"
                            } else {
                                statusLabel.text = "WSL Conda/Sage probe failed"
                            }
                        }
                        ExecutionMode.DOCKER -> {
                            val result = value as? RuntimeOperationResult<*>
                            if (error == null && result?.succeeded == true) {
                                statusLabel.text = "Validated image-owned Sage probe: $containerImage"
                            } else {
                                statusLabel.text = result?.diagnostics?.firstOrNull()?.message ?: "Container Sage probe failed"
                            }
                        }
                        ExecutionMode.SSH -> statusLabel.text = "SSH runtime discovery is unsupported; configure and validate explicit paths"
                    }
                }
            }
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
        c.gridy = 2
        c.gridx = 0
        c.gridwidth = 2
        c.weighty = 0.0
        panel.add(JLabel("Additional sage parameters:"), c)
        c.gridy = 3
        c.gridx = 0
        c.gridwidth = 2
        panel.add(sageParametersField, c)
        c.gridy = 4
        c.weighty = 0.0
        panel.add(detectButton, c)
        c.gridy = 5
        panel.add(statusLabel, c)
        rootComponent = panel
        return panel
    }

    override fun isModified(): Boolean {
        val s = SageRunSettings.getInstance().getState()
        return s.executionMode != (modeCombo.selectedItem as ExecutionMode).name ||
            s.nativeSageExecutable != nativeSageExecutableField.text ||
            s.wslSageExecutable != wslSageExecutableField.text ||
            s.sageParameters != sageParametersField.text ||
            s.wslDistribution != wslDistributionField.text ||
            s.wslCondaEnvironment != wslCondaEnvironmentField.text ||
            s.wslCondaExecutable != wslCondaExecutableField.text ||
            s.containerExecutable != containerExecutableField.text ||
            s.dockerImage != dockerImageField.text ||
            s.dockerContainerDir != dockerContainerDirField.text ||
            s.dockerCommand != dockerCommandField.text ||
            s.sshHost != sshHostField.text ||
            s.sshUser != sshUserField.text ||
            s.sshPort.toString() != sshPortField.text ||
            s.sshKnownHostsFile != sshKnownHostsField.text ||
            s.sshAuthentication != sshAuthenticationField.text ||
            s.sshIdentityFile != sshIdentityField.text ||
            s.sshRuntimeRoot != sshRuntimeRootField.text ||
            s.sshSageExecutable != sshSageExecutableField.text ||
            s.sshLocalRoot != sshLocalRootField.text ||
            s.sshTargetRoot != sshTargetRootField.text ||
            s.sshConnectTimeoutSeconds.toString() != sshTimeoutField.text
    }

    override fun apply() {
        invalidateDetection()
        val mode = modeCombo.selectedItem as ExecutionMode
        val port = parsePort()
        val timeout = parseTimeout()
        val candidate = SageRunSettings.State().apply {
            executionMode = mode.name
            nativeSageExecutable = nativeSageExecutableField.text
            wslSageExecutable = wslSageExecutableField.text
            sageParameters = sageParametersField.text
            wslDistribution = wslDistributionField.text
            wslCondaEnvironment = wslCondaEnvironmentField.text
            wslCondaExecutable = wslCondaExecutableField.text
            containerExecutable = containerExecutableField.text
            dockerImage = dockerImageField.text
            dockerContainerDir = dockerContainerDirField.text
            dockerCommand = dockerCommandField.text
            sshHost = sshHostField.text
            sshUser = sshUserField.text
            sshPort = port
            sshKnownHostsFile = sshKnownHostsField.text
            sshAuthentication = sshAuthenticationField.text
            sshIdentityFile = sshIdentityField.text
            sshRuntimeRoot = sshRuntimeRootField.text
            sshSageExecutable = sshSageExecutableField.text
            sshLocalRoot = sshLocalRootField.text
            sshTargetRoot = sshTargetRootField.text
            sshConnectTimeoutSeconds = timeout
        }
        validateCandidate(mode, candidate)
        if (mode == ExecutionMode.NATIVE && candidate.nativeSageExecutable.isBlank()) {
            throw ConfigurationException("Native Sage executable must be configured or discovered with Detect before Apply")
        }
        SageRunSettings.getInstance().loadState(candidate)
    }

    private fun parsePort(): Int = sshPortField.text.trim().toIntOrNull()?.takeIf { it in 1..65535 }
        ?: throw ConfigurationException("SSH port must be an integer between 1 and 65535")

    private fun parseTimeout(): Int = sshTimeoutField.text.trim().toIntOrNull()?.takeIf { it in 1..300 }
        ?: throw ConfigurationException("SSH connect timeout must be an integer between 1 and 300 seconds")

    private fun validateCandidate(mode: ExecutionMode, candidate: SageRunSettings.State) {
        val result: RuntimeOperationResult<*> = when (mode) {
            ExecutionMode.NATIVE -> RuntimeOperationResult(Unit)
            ExecutionMode.WSL -> runCatching {
                SageAutoDetect.validateConfiguredWslSettings(candidate.wslDistribution, candidate.wslCondaEnvironment, candidate.wslCondaExecutable, candidate.wslSageExecutable)
                RuntimeOperationResult(Unit)
            }.getOrElse { RuntimeOperationResult(null, listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.TARGET_INVALID, "WSL_CONFIG_VALIDATE", it.message ?: "WSL settings are invalid")), false) }
            ExecutionMode.DOCKER -> SageRuntimeService.getInstance().validateContainerProfile(candidate)
            ExecutionMode.SSH -> SageRuntimeService.getInstance().validateSshSettings(candidate)
        }
        if (!result.succeeded) {
            throw ConfigurationException(result.diagnostics.firstOrNull()?.message ?: "Selected Sage runtime settings are invalid")
        }
    }

    override fun reset() {
        invalidateDetection()
        val s = SageRunSettings.getInstance().getState()
        statusLabel.text = ""
        modeCombo.selectedItem = runCatching { ExecutionMode.valueOf(s.executionMode) }.getOrDefault(ExecutionMode.WSL)
        nativeSageExecutableField.text = s.nativeSageExecutable
        wslSageExecutableField.text = s.wslSageExecutable
        sageParametersField.text = s.sageParameters
        wslDistributionField.text = s.wslDistribution
        wslCondaEnvironmentField.text = s.wslCondaEnvironment
        wslCondaExecutableField.text = s.wslCondaExecutable
        containerExecutableField.text = s.containerExecutable
        dockerImageField.text = s.dockerImage
        dockerContainerDirField.text = s.dockerContainerDir
        dockerCommandField.text = s.dockerCommand
        sshHostField.text = s.sshHost
        sshUserField.text = s.sshUser
        sshPortField.text = s.sshPort.toString()
        sshKnownHostsField.text = s.sshKnownHostsFile
        sshAuthenticationField.text = s.sshAuthentication
        sshIdentityField.text = s.sshIdentityFile
        sshRuntimeRootField.text = s.sshRuntimeRoot
        sshSageExecutableField.text = s.sshSageExecutable
        sshLocalRootField.text = s.sshLocalRoot
        sshTargetRootField.text = s.sshTargetRoot
        sshTimeoutField.text = s.sshConnectTimeoutSeconds.toString()
        (cards.layout as CardLayout).show(cards, (modeCombo.selectedItem as ExecutionMode).name)
    }

    private fun invalidateDetection() {
        activeProbe?.cancel()
        activeProbe = null
        detectRequest++
        detectButton.isEnabled = true
    }

    override fun disposeUIResources() {
        invalidateDetection()
        rootComponent = null
    }
}
