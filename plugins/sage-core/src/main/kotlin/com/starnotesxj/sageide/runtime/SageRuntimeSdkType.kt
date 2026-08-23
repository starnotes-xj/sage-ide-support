package com.starnotesxj.sageide.runtime

import com.intellij.openapi.options.ConfigurationException
import com.intellij.openapi.project.Project
import com.intellij.openapi.projectRoots.AdditionalDataConfigurable
import com.intellij.openapi.projectRoots.Sdk
import com.intellij.openapi.projectRoots.SdkAdditionalData
import com.intellij.openapi.projectRoots.SdkModel
import com.intellij.openapi.projectRoots.SdkModificator
import com.intellij.openapi.projectRoots.SdkType
import com.intellij.openapi.ui.ComboBox
import com.intellij.openapi.ui.Messages
import com.intellij.ui.components.JBTextField
import com.intellij.util.ui.JBUI
import com.starnotesxj.sageide.sugar.SageIcons
import com.starnotesxj.sagemath.runtime.InstalledRuntime
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import org.jdom.Element
import java.awt.GridBagConstraints
import java.awt.GridBagLayout
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.util.function.Consumer
import javax.swing.JComponent
import javax.swing.JLabel
import javax.swing.JPanel

/** IntelliJ SDK type for a verified, externally hosted SageMath runtime. */
class SageRuntimeSdkType private constructor() : SdkType(NAME) {
    @Suppress("DEPRECATION")
    @Deprecated("IntelliJ keeps this compatibility override; use suggestHomePaths(Project?)")
    override fun suggestHomePath(): String? = null

    override fun suggestHomePaths(project: Project?): MutableCollection<String> =
        SageRuntimeSdkService.getInstance().installedRuntimes().map { it.root.toString() }.toMutableList()

    override fun isValidSdkHome(path: String): Boolean = runCatching {
        val candidate = Path.of(path).toAbsolutePath().normalize()
        Files.isDirectory(candidate, LinkOption.NOFOLLOW_LINKS) && !Files.isSymbolicLink(candidate)
    }.getOrDefault(false)

    override fun suggestSdkName(currentSdkName: String?, sdkHome: String): String =
        currentSdkName?.takeIf { it.isNotBlank() } ?: "SageMath Runtime (${Path.of(sdkHome).fileName})"

    override fun createAdditionalDataConfigurable(
        sdkModel: SdkModel,
        sdkModificator: SdkModificator,
    ): AdditionalDataConfigurable? = SageRuntimeSdkAdditionalDataConfigurable(sdkModificator)

    override fun saveAdditionalData(additionalData: SdkAdditionalData, additional: Element) {
        (additionalData as? SageRuntimeSdkAdditionalData)?.save(additional)
    }

    override fun loadAdditionalData(currentSdk: Sdk, additional: Element): SdkAdditionalData? =
        SageRuntimeSdkAdditionalData.load(additional)

    override fun getPresentableName(): String = "SageMath Runtime"

    override fun getIcon() = SageIcons.SAGE

    override fun getVersionString(sdk: Sdk): String? =
        (sdk.sdkAdditionalData as? SageRuntimeSdkAdditionalData)?.runtimeId?.version
            ?: sdk.versionString
            ?: sdk.homePath?.let { "managed runtime at $it" }

    override fun sdkHasValidPath(sdk: Sdk): Boolean =
        sdk.homePath?.let(::isValidSdkHome) == true && sdk.sdkAdditionalData is SageRuntimeSdkAdditionalData

    override fun isLocalSdk(sdk: Sdk): Boolean =
        (sdk.sdkAdditionalData as? SageRuntimeSdkAdditionalData)?.target == RuntimeTarget.Native

    override fun supportsCustomCreateUI(): Boolean = true

    override fun showCustomCreateUI(
        sdkModel: SdkModel,
        parentComponent: JComponent,
        selectedSdk: Sdk?,
        sdkCreatedCallback: Consumer<in Sdk>,
    ) {
        val runtimes = SageRuntimeSdkService.getInstance().installedRuntimes()
        if (runtimes.isEmpty()) {
            Messages.showInfoMessage(
                parentComponent,
                "Install a verified SageMath runtime from the Runtime Manager before adding an SDK.",
                "SageMath Runtime",
            )
            return
        }
        val labels = runtimes.map { SageRuntimeSdkDisplay.runtimeLabel(it.id) }.toTypedArray()
        @Suppress("DEPRECATION")
        val selected = Messages.showChooseDialog(
            "Select a verified SageMath runtime:",
            "SageMath Runtime",
            labels,
            labels.first(),
            SageIcons.SAGE,
        )
        if (selected < 0) return
        val result = SageRuntimeSdkService.getInstance().createSdk(
            sdkModel,
            runtimes[selected],
            RuntimeTarget.Native,
        )
        result.value?.let(sdkCreatedCallback::accept)
            ?: Messages.showErrorDialog(
                parentComponent,
                result.diagnostics.joinToString("\n") { it.message },
                "Cannot Add SageMath Runtime",
            )
    }

    companion object {
        const val NAME: String = "SageMath Runtime SDK"

        @JvmStatic
        fun getInstance(): SageRuntimeSdkType = findInstance(SageRuntimeSdkType::class.java)
    }
}

private class SageRuntimeSdkAdditionalDataConfigurable(
    private val sdkModificator: SdkModificator,
) : AdditionalDataConfigurable {
    private enum class TargetKind { NATIVE, WSL, DOCKER, SSH }

    private var sdk: Sdk? = null
    private var workingData: SageRuntimeSdkAdditionalData? = null
    private var initial: SageRuntimeSdkAdditionalData? = null
    private val targetKind = ComboBox(TargetKind.entries.toTypedArray())
    private val detailsField = JBTextField()
    private val userField = JBTextField()
    private val portField = JBTextField("22")
    private val statusLabel = JLabel()
    private var component: JPanel? = null

    override fun setSdk(sdk: Sdk) {
        this.sdk = sdk
        val data = sdkModificator.sdkAdditionalData as? SageRuntimeSdkAdditionalData
        workingData = data?.copyData()
        initial = workingData?.copyData()
        reset()
    }

    override fun getTabName(): String = "Sage Runtime"

    override fun createComponent(): JComponent {
        component?.let { return it }
        val panel = JPanel(GridBagLayout())
        fun row(y: Int, label: String, field: JComponent) {
            val left = GridBagConstraints().apply {
                gridx = 0; gridy = y; anchor = GridBagConstraints.WEST; insets = JBUI.insets(4)
            }
            val right = GridBagConstraints().apply {
                gridx = 1; gridy = y; weightx = 1.0; fill = GridBagConstraints.HORIZONTAL; insets = JBUI.insets(4)
            }
            panel.add(JLabel(label), left)
            panel.add(field, right)
        }
        row(0, "Target:", targetKind)
        row(1, "Distribution / image / host:", detailsField)
        row(2, "SSH user:", userField)
        row(3, "SSH port:", portField)
        row(4, "Validation:", statusLabel)
        targetKind.addActionListener { updateFieldVisibility() }
        updateFieldVisibility()
        component = panel
        return panel
    }

    override fun isModified(): Boolean {
        val before = initial ?: return false
        val current = targetFromFieldsSafely() ?: return true
        return before.target != current
    }

    override fun disposeUIResources() {
        sdk = null
        workingData = null
        initial = null
        component = null
    }

    override fun apply() {
        val data = workingData ?: throw ConfigurationException("SageMath SDK metadata is missing")
        val target = targetFromFieldsSafely()
            ?: throw ConfigurationException("SageMath target fields are invalid")
        val result = SageRuntimeSdkService.getInstance().validate(data.runtimeId, target)
        if (!result.succeeded) {
            statusLabel.text = result.diagnostics.firstOrNull()?.message ?: "Runtime validation failed"
            throw ConfigurationException(statusLabel.text)
        }
        data.target = target
        sdkModificator.setSdkAdditionalData(data)
        initial = data.copyData()
        statusLabel.text = "Valid: ${SageRuntimeSdkDisplay.targetLabel(target)}"
    }

    override fun reset() {
        workingData = initial?.copyData()
        val data = workingData
        val target = data?.target ?: RuntimeTarget.Native
        when (target) {
            RuntimeTarget.Native -> {
                targetKind.selectedItem = TargetKind.NATIVE
                detailsField.text = ""
                userField.text = ""
                portField.text = "22"
            }
            is RuntimeTarget.Wsl -> {
                targetKind.selectedItem = TargetKind.WSL
                detailsField.text = target.distribution
                userField.text = ""
                portField.text = "22"
            }
            is RuntimeTarget.Docker -> {
                targetKind.selectedItem = TargetKind.DOCKER
                detailsField.text = target.image
                userField.text = ""
                portField.text = "22"
            }
            is RuntimeTarget.RemoteSsh -> {
                targetKind.selectedItem = TargetKind.SSH
                detailsField.text = target.host
                userField.text = target.user.orEmpty()
                portField.text = target.port.toString()
            }
        }
        updateFieldVisibility()
        statusLabel.text = ""
    }

    private fun targetFromFields(): RuntimeTarget = when (targetKind.selectedItem as TargetKind) {
        TargetKind.NATIVE -> RuntimeTarget.Native
        TargetKind.WSL -> RuntimeTarget.Wsl(detailsField.text.trim())
        TargetKind.DOCKER -> RuntimeTarget.Docker(detailsField.text.trim())
        TargetKind.SSH -> RuntimeTarget.RemoteSsh(
            host = detailsField.text.trim(),
            user = userField.text.trim().takeIf { it.isNotEmpty() },
            port = portField.text.trim().toIntOrNull() ?: 22,
        )
    }

    private fun targetFromFieldsSafely(): RuntimeTarget? = runCatching { targetFromFields() }.getOrNull()

    private fun updateFieldVisibility() {
        val ssh = targetKind.selectedItem == TargetKind.SSH
        detailsField.toolTipText = when (targetKind.selectedItem) {
            TargetKind.NATIVE -> "Uses the local host"
            TargetKind.WSL -> "WSL distribution name"
            TargetKind.DOCKER -> "Docker image reference"
            TargetKind.SSH -> "Remote SSH host"
            else -> null
        }
        userField.isEnabled = ssh
        portField.isEnabled = ssh
    }
}
