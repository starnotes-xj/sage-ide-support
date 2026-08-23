package com.starnotesxj.sageide.run

import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.execution.configurations.ConfigurationType
import com.intellij.execution.configurations.ConfigurationTypeUtil
import com.intellij.execution.configurations.RunConfiguration
import com.intellij.execution.configurations.RuntimeConfigurationException
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.project.Project
import com.jetbrains.python.run.AbstractPythonRunConfiguration
import com.jetbrains.python.run.DebugAwareConfiguration
import com.starnotesxj.sageide.sugar.SageIcons

/**
 * Sage run configurations execute the verified manifest launcher; the bundled
 * Python path is resolved separately for Python-dependent debug consumers.
 * Design follows renpe/intellij-sagemath (Apache 2.0).
 */
class SageRunConfiguration(
    project: Project,
    factory: ConfigurationFactory,
) : AbstractPythonRunConfiguration<SageRunConfiguration>(project, factory), DebugAwareConfiguration {

    var scriptPath: String = ""

    var scriptParameters: String = ""

    override fun getState(executor: com.intellij.execution.Executor, environment: ExecutionEnvironment) =
        if (executor.id == "Debug") {
            SageDebugCommandLineState(this, environment)
        } else {
            SageCommandLineState(this, environment)
        }

    override fun createConfigurationEditor() = SageRunSettingsEditor()

    override fun canRunUnderDebug(): Boolean = true

    override fun checkConfiguration() {
        // Sage execution is launcher-based, but the launcher must come from a
        // verified Runtime SDK whose manifest declares bundled Python. This
        // avoids silently falling back to an unrelated system interpreter.
        if (scriptPath.isBlank()) {
            throw RuntimeConfigurationException("The Sage script path is empty")
        }
        val target = when (runTargetMode()) {
            ExecutionMode.NATIVE -> com.starnotesxj.sagemath.runtime.RuntimeTarget.Native
            ExecutionMode.WSL -> com.starnotesxj.sagemath.runtime.RuntimeTarget.Wsl(SageRunSettings.getInstance().getState().wslDistribution)
            ExecutionMode.DOCKER -> com.starnotesxj.sagemath.runtime.RuntimeTarget.Docker(SageRunSettings.getInstance().getState().dockerImage)
        }
        val resolution = com.starnotesxj.sageide.runtime.SageRuntimeSdkService.getInstance().currentExecutables(target)
        if (!resolution.succeeded) {
            throw RuntimeConfigurationException(resolution.diagnostics.firstOrNull()?.message ?: "The bundled SageMath Python is unavailable")
        }
    }

    private fun runTargetMode(): ExecutionMode =
        runCatching { ExecutionMode.valueOf(SageRunSettings.getInstance().getState().executionMode) }.getOrDefault(ExecutionMode.NATIVE)

    override fun writeExternal(element: org.jdom.Element) {
        super<AbstractPythonRunConfiguration>.writeExternal(element)
        element.setAttribute("scriptPath", scriptPath)
        element.setAttribute("scriptParameters", scriptParameters)
    }

    override fun readExternal(element: org.jdom.Element) {
        super<AbstractPythonRunConfiguration>.readExternal(element)
        scriptPath = element.getAttributeValue("scriptPath") ?: ""
        scriptParameters = element.getAttributeValue("scriptParameters") ?: ""
    }
}

class SageConfigurationFactory(type: ConfigurationType) : ConfigurationFactory(type) {
    override fun getId(): String = "SageMath"

    override fun createTemplateConfiguration(project: Project): RunConfiguration =
        SageRunConfiguration(project, this).also { it.name = "SageMath" }
}

class SageRunConfigurationType : ConfigurationType {
    override fun getDisplayName(): String = "SageMath"
    override fun getConfigurationTypeDescription(): String = "SageMath run configuration"
    override fun getIcon() = SageIcons.SAGE
    override fun getId(): String = "SageRunConfiguration"
    override fun getConfigurationFactories(): Array<ConfigurationFactory> = arrayOf(SageConfigurationFactory(this))

    companion object {
        @JvmStatic
        fun getInstance(): SageRunConfigurationType =
            ConfigurationTypeUtil.findConfigurationType(SageRunConfigurationType::class.java)
    }
}
