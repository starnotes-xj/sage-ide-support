package com.starnotesxj.sageide.run

import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.execution.configurations.ConfigurationType
import com.intellij.execution.configurations.ConfigurationTypeUtil
import com.intellij.execution.configurations.RunConfiguration
import com.intellij.execution.configurations.RunConfigurationBase
import com.intellij.execution.configurations.RunConfigurationOptions
import com.intellij.execution.configurations.RuntimeConfigurationException
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.project.Project
import com.starnotesxj.sageide.sugar.SageIcons

/**
 * Sage run configurations: a Sage script executed through the `sage` command
 * (native or via WSL), never through a Python interpreter.
 * Design follows renpe/intellij-sagemath (Apache 2.0).
 */
class SageRunConfiguration(
    project: Project,
    factory: ConfigurationFactory,
    name: String,
) : RunConfigurationBase<RunConfigurationOptions>(project, factory, name) {

    var scriptPath: String = ""

    var scriptParameters: String = ""

    override fun getState(executor: com.intellij.execution.Executor, environment: ExecutionEnvironment) =
        SageCommandLineState(this, environment)

    override fun getConfigurationEditor() = SageRunSettingsEditor()

    override fun checkConfiguration() {
        if (scriptPath.isBlank()) {
            throw RuntimeConfigurationException("The Sage script path is empty")
        }
    }

    override fun writeExternal(element: org.jdom.Element) {
        super.writeExternal(element)
        element.setAttribute("scriptPath", scriptPath)
        element.setAttribute("scriptParameters", scriptParameters)
    }

    override fun readExternal(element: org.jdom.Element) {
        super.readExternal(element)
        scriptPath = element.getAttributeValue("scriptPath") ?: ""
        scriptParameters = element.getAttributeValue("scriptParameters") ?: ""
    }
}

class SageConfigurationFactory(type: ConfigurationType) : ConfigurationFactory(type) {
    override fun getId(): String = "SageMath"

    override fun createTemplateConfiguration(project: Project): RunConfiguration =
        SageRunConfiguration(project, this, "SageMath")
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
