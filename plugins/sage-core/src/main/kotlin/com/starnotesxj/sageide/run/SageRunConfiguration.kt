package com.starnotesxj.sageide.run

import com.intellij.execution.configurations.ConfigurationFactory
import com.intellij.execution.configurations.ConfigurationType
import com.intellij.execution.configurations.ConfigurationTypeUtil
import com.intellij.execution.configurations.RunConfiguration
import com.intellij.execution.configurations.RuntimeConfigurationException
import com.intellij.execution.runners.ExecutionEnvironment
import com.intellij.openapi.project.Project
import com.intellij.openapi.projectRoots.ProjectJdkTable
import com.intellij.openapi.projectRoots.Sdk
import com.intellij.openapi.roots.ProjectRootManager
import com.intellij.openapi.util.JDOMExternalizerUtil
import com.jetbrains.python.run.AbstractPythonRunConfiguration
import com.jetbrains.python.run.DebugAwareConfiguration
import com.starnotesxj.sageide.runtime.SageRuntimeSdkService
import com.starnotesxj.sageide.sugar.SageIcons
import com.starnotesxj.sagemath.runtime.ResolvedRuntimeExecutables
import com.starnotesxj.sagemath.runtime.RuntimeDiagnostic
import com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode
import com.starnotesxj.sagemath.runtime.RuntimeOperationResult

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

    /** Optional explicit SDK name; blank means inherit the project SDK. */
    var sageSdkName: String? = null

    fun resolveSageSdk(): RuntimeOperationResult<Sdk> {
        val name = sageSdkName?.trim().orEmpty()
        val sdk = if (name.isNotEmpty()) {
            ProjectJdkTable.getInstance().findJdk(name)
        }
        else {
            ProjectRootManager.getInstance(project).projectSdk
        }
        if (sdk == null) {
            return RuntimeOperationResult(
                null,
                listOf(
                    RuntimeDiagnostic(
                        RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED,
                        "RUN_SDK_RESOLVE",
                        if (name.isNotEmpty()) "Configured SageMath SDK was not found" else "Project SDK is not configured",
                    ),
                ),
                false,
            )
        }
        return RuntimeOperationResult(sdk)
    }

    fun resolveSageExecutables(): RuntimeOperationResult<ResolvedRuntimeExecutables> =
        resolveSageSdk().let { result ->
            if (!result.succeeded) RuntimeOperationResult(null, result.diagnostics, false)
            else SageRuntimeSdkService.getInstance().resolveSdkExecutables(result.value!!)
        }

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
        val resolution = resolveSageExecutables()
        if (!resolution.succeeded) {
            throw RuntimeConfigurationException(resolution.diagnostics.firstOrNull()?.message ?: "The bundled SageMath Python is unavailable")
        }
    }

    override fun writeExternal(element: org.jdom.Element) {
        super<AbstractPythonRunConfiguration>.writeExternal(element)
        element.setAttribute("scriptPath", scriptPath)
        element.setAttribute("scriptParameters", scriptParameters)
        JDOMExternalizerUtil.writeField(element, "SAGE_SDK_NAME", sageSdkName)
    }

    override fun readExternal(element: org.jdom.Element) {
        super<AbstractPythonRunConfiguration>.readExternal(element)
        scriptPath = element.getAttributeValue("scriptPath") ?: ""
        scriptParameters = element.getAttributeValue("scriptParameters") ?: ""
        sageSdkName = JDOMExternalizerUtil.readField(element, "SAGE_SDK_NAME")?.takeIf { it.isNotBlank() }
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
