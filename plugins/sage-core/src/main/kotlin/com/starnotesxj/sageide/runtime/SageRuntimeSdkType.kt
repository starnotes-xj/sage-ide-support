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
import com.starnotesxj.sageide.SageBundle
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
        currentSdkName?.takeIf { it.isNotBlank() }
            ?: SageBundle.message("runtime.sdk.name", Path.of(sdkHome).fileName)

    override fun createAdditionalDataConfigurable(
        sdkModel: SdkModel,
        sdkModificator: SdkModificator,
    ): AdditionalDataConfigurable? = SageRuntimeSdkAdditionalDataConfigurable(sdkModificator)

    override fun saveAdditionalData(additionalData: SdkAdditionalData, additional: Element) {
        (additionalData as? SageRuntimeSdkAdditionalData)?.save(additional)
    }

    override fun loadAdditionalData(currentSdk: Sdk, additional: Element): SdkAdditionalData? =
        SageRuntimeSdkAdditionalData.load(additional)

    override fun getPresentableName(): String = SageBundle.message("runtime.sdk.presentable.name")

    override fun getIcon() = SageIcons.SAGE

    override fun getVersionString(sdk: Sdk): String? =
        (sdk.sdkAdditionalData as? SageRuntimeSdkAdditionalData)?.runtimeId?.version
            ?: sdk.versionString
            ?: sdk.homePath?.let { SageBundle.message("runtime.sdk.managed.location", it) }

    override fun sdkHasValidPath(sdk: Sdk): Boolean =
        SageRuntimeSdkService.getInstance().sdkAdapter.validate(sdk).succeeded

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
                SageBundle.message("runtime.sdk.install.first"),
                SageBundle.message("runtime.sdk.presentable.name"),
            )
            return
        }
        val labels = runtimes.map { SageRuntimeSdkDisplay.runtimeLabel(it.id) }.toTypedArray()
        @Suppress("DEPRECATION")
        val selected = Messages.showChooseDialog(
            SageBundle.message("runtime.sdk.choose"),
            SageBundle.message("runtime.sdk.presentable.name"),
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
                SageBundle.message("runtime.sdk.add.failed"),
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
    private enum class TargetKind {
        NATIVE,
        WSL,
        DOCKER,
        SSH;

        override fun toString(): String = SageBundle.message("runtime.sdk.target.$name")
    }

    private var sdk: Sdk? = null
    private var workingData: SageRuntimeSdkAdditionalData? = null
    private var initial: SageRuntimeSdkAdditionalData? = null
    private val targetKind = ComboBox(TargetKind.entries.toTypedArray())
    private val containerEngine = ComboBox(com.starnotesxj.sagemath.runtime.ContainerEngine.entries.toTypedArray())
    private val detailsField = JBTextField()
    private val userField = JBTextField()
    private val portField = JBTextField("22")
    private val runtimeRootField = JBTextField()
    private val mappingLocalRootField = JBTextField()
    private val mappingTargetRootField = JBTextField()
    private val statusLabel = JLabel()
    private var component: JPanel? = null

    override fun setSdk(sdk: Sdk) {
        this.sdk = sdk
        val data = sdkModificator.sdkAdditionalData as? SageRuntimeSdkAdditionalData
        workingData = data?.copyData()
        initial = workingData?.copyData()
        reset()
    }

    override fun getTabName(): String = SageBundle.message("runtime.sdk.tab")

    override fun createComponent(): JComponent {
        component?.let { return it }
        val panel = JPanel(GridBagLayout())
        fun row(y: Int, label: String, field: JComponent): JLabel {
            val left = GridBagConstraints().apply {
                gridx = 0; gridy = y; anchor = GridBagConstraints.WEST; insets = JBUI.insets(4)
            }
            val right = GridBagConstraints().apply {
                gridx = 1; gridy = y; weightx = 1.0; fill = GridBagConstraints.HORIZONTAL; insets = JBUI.insets(4)
            }
            val labelComponent = JLabel(label)
            panel.add(labelComponent, left)
            panel.add(field, right)
            return labelComponent
        }
        row(0, SageBundle.message("runtime.sdk.label.target"), targetKind)
        val containerEngineLabel = row(1, SageBundle.message("runtime.sdk.label.container.engine"), containerEngine)
        containerEngine.putClientProperty("sage.label", containerEngineLabel)
        row(2, SageBundle.message("runtime.sdk.label.details"), detailsField)
        row(3, SageBundle.message("runtime.sdk.label.ssh.user"), userField)
        row(4, SageBundle.message("runtime.sdk.label.ssh.port"), portField)
        val runtimeRootLabel = row(5, SageBundle.message("runtime.sdk.label.ssh.runtime.root"), runtimeRootField)
        val mappingLocalLabel = row(6, SageBundle.message("runtime.sdk.label.mapping.local"), mappingLocalRootField)
        val mappingTargetLabel = row(7, SageBundle.message("runtime.sdk.label.mapping.target"), mappingTargetRootField)
        row(8, SageBundle.message("runtime.sdk.label.validation"), statusLabel)
        runtimeRootField.putClientProperty("sage.label", runtimeRootLabel)
        mappingLocalRootField.putClientProperty("sage.label", mappingLocalLabel)
        mappingTargetRootField.putClientProperty("sage.label", mappingTargetLabel)
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
        val data = workingData ?: throw ConfigurationException(SageBundle.message("runtime.sdk.error.metadata"))
        val target = targetFromFieldsSafely()
            ?: throw ConfigurationException(SageBundle.message("runtime.sdk.error.target"))
        val result = SageRuntimeSdkService.getInstance().validate(data.runtimeId, target)
        if (!result.succeeded) {
            statusLabel.text = result.diagnostics.firstOrNull()?.message ?: SageBundle.message("runtime.sdk.status.failed")
            throw ConfigurationException(statusLabel.text)
        }
        data.target = target
        sdkModificator.setSdkAdditionalData(data)
        initial = data.copyData()
        statusLabel.text = SageBundle.message("runtime.sdk.status.valid", SageRuntimeSdkDisplay.targetLabel(target))
    }

    override fun reset() {
        workingData = initial?.copyData()
        val data = workingData
        val target = data?.target ?: RuntimeTarget.Native
        when (target) {
            RuntimeTarget.Native -> {
                targetKind.selectedItem = TargetKind.NATIVE
                containerEngine.selectedItem = com.starnotesxj.sagemath.runtime.ContainerEngine.DOCKER
                detailsField.text = ""
                userField.text = ""
                portField.text = "22"
                runtimeRootField.text = ""
                mappingLocalRootField.text = ""
                mappingTargetRootField.text = ""
            }
            is RuntimeTarget.Wsl -> {
                targetKind.selectedItem = TargetKind.WSL
                containerEngine.selectedItem = com.starnotesxj.sagemath.runtime.ContainerEngine.DOCKER
                detailsField.text = target.distribution
                userField.text = ""
                portField.text = "22"
                runtimeRootField.text = ""
                mappingLocalRootField.text = target.pathMapping?.localRoot?.toString().orEmpty()
                mappingTargetRootField.text = target.pathMapping?.targetRoot.orEmpty()
            }
            is RuntimeTarget.Docker -> {
                targetKind.selectedItem = TargetKind.DOCKER
                containerEngine.selectedItem = target.engine
                detailsField.text = target.image
                userField.text = ""
                portField.text = "22"
                runtimeRootField.text = ""
                mappingLocalRootField.text = target.pathMapping?.localRoot?.toString().orEmpty()
                mappingTargetRootField.text = target.pathMapping?.targetRoot.orEmpty()
            }
            is RuntimeTarget.RemoteSsh -> {
                targetKind.selectedItem = TargetKind.SSH
                containerEngine.selectedItem = com.starnotesxj.sagemath.runtime.ContainerEngine.DOCKER
                detailsField.text = target.host
                userField.text = target.user.orEmpty()
                portField.text = target.port.toString()
                runtimeRootField.text = target.runtimeRoot.orEmpty()
                mappingLocalRootField.text = target.pathMapping?.localRoot?.toString().orEmpty()
                mappingTargetRootField.text = target.pathMapping?.targetRoot.orEmpty()
            }
        }
        updateFieldVisibility()
        statusLabel.text = ""
    }

    private fun targetFromFields(): RuntimeTarget = when (targetKind.selectedItem as TargetKind) {
        TargetKind.NATIVE -> RuntimeTarget.Native
        TargetKind.WSL -> RuntimeTarget.Wsl(detailsField.text.trim(), pathMapping = mappingFromFields())
        TargetKind.DOCKER -> RuntimeTarget.Docker(
            detailsField.text.trim(),
            pathMapping = mappingFromFields(),
            engine = containerEngine.selectedItem as com.starnotesxj.sagemath.runtime.ContainerEngine,
        )
        TargetKind.SSH -> RuntimeTarget.RemoteSsh(
            host = detailsField.text.trim(),
            user = userField.text.trim().takeIf { it.isNotEmpty() },
            port = portField.text.trim().toIntOrNull() ?: 22,
            runtimeRoot = runtimeRootField.text.trim().takeIf { it.isNotEmpty() },
            pathMapping = mappingFromFields(),
        )
    }

    private fun mappingFromFields(): com.starnotesxj.sagemath.runtime.RuntimePathMapping? {
        val local = mappingLocalRootField.text.trim()
        val target = mappingTargetRootField.text.trim()
        if (local.isEmpty() && target.isEmpty()) return null
        if (local.isEmpty() || target.isEmpty()) error("Both mapping roots are required")
        return com.starnotesxj.sagemath.runtime.RuntimePathMapping(Path.of(local), target)
    }

    private fun targetFromFieldsSafely(): RuntimeTarget? = runCatching { targetFromFields() }.getOrNull()

    private fun updateFieldVisibility() {
        val ssh = targetKind.selectedItem == TargetKind.SSH
        val mapped = targetKind.selectedItem == TargetKind.WSL || targetKind.selectedItem == TargetKind.DOCKER || ssh
        containerEngine.isVisible = targetKind.selectedItem == TargetKind.DOCKER
        containerEngine.isEnabled = targetKind.selectedItem == TargetKind.DOCKER
        runtimeRootField.isVisible = ssh
        mappingLocalRootField.isVisible = mapped
        mappingTargetRootField.isVisible = mapped
        (containerEngine.getClientProperty("sage.label") as? JComponent)?.isVisible = targetKind.selectedItem == TargetKind.DOCKER
        (runtimeRootField.getClientProperty("sage.label") as? JComponent)?.isVisible = ssh
        (mappingLocalRootField.getClientProperty("sage.label") as? JComponent)?.isVisible = mapped
        (mappingTargetRootField.getClientProperty("sage.label") as? JComponent)?.isVisible = mapped
        detailsField.toolTipText = when (targetKind.selectedItem) {
            TargetKind.NATIVE -> SageBundle.message("runtime.sdk.tooltip.native")
            TargetKind.WSL -> SageBundle.message("runtime.sdk.tooltip.wsl")
            TargetKind.DOCKER -> SageBundle.message("runtime.sdk.tooltip.docker")
            TargetKind.SSH -> SageBundle.message("runtime.sdk.tooltip.ssh")
            else -> null
        }
        userField.isEnabled = ssh
        portField.isEnabled = ssh
        runtimeRootField.isEnabled = ssh
        runtimeRootField.toolTipText = SageBundle.message("runtime.sdk.tooltip.ssh.runtime.root")
    }
}
