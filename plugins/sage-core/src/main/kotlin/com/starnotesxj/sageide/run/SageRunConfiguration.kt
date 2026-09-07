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
import com.starnotesxj.sageide.runtime.SageRuntimeSdkType
import com.starnotesxj.sageide.sugar.SageIcons
import com.starnotesxj.sagemath.runtime.ResolvedRuntimeExecutables
import com.starnotesxj.sagemath.runtime.RuntimeDiagnostic
import com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode
import com.starnotesxj.sagemath.runtime.RuntimeOperationResult

/**
 * Performs only local run-configuration validation. It must not resolve or probe
 * an external runtime because IntelliJ may call it under a ReadAction.
 */
internal fun configurationValidationError(scriptPath: String, settings: SageRunSettings.State): String? {
    if (scriptPath.isBlank()) return "The Sage script path is empty"
    val mode = runCatching { ExecutionMode.valueOf(settings.executionMode) }
        .getOrElse { return "Unknown Sage execution mode: " + settings.executionMode }
    return when (mode) {
        ExecutionMode.NATIVE -> null
        ExecutionMode.WSL -> runCatching {
            SageAutoDetect.validateConfiguredWslSettings(
                settings.wslDistribution,
                settings.wslCondaEnvironment,
                settings.wslCondaExecutable,
                settings.wslSageExecutable,
                settings.wslPythonExecutable,
            )
        }.exceptionOrNull()?.message
        ExecutionMode.DOCKER -> {
            val profile = com.starnotesxj.sagemath.runtime.ContainerProfileValidator.validate(
                settings.containerExecutable,
                settings.dockerImage,
                settings.dockerCommand,
                settings.dockerContainerDir,
            )
            if (profile.succeeded) null else profile.diagnostics.firstOrNull()?.message ?: "Container Sage settings are invalid"
        }
        // SSH resolution is intentionally deferred to execution: it may inspect
        // user files and the transport is not needed for icon validation.
        ExecutionMode.SSH -> null
    }
}

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

    /**
     * Settings-backed WSL runs must not probe the host before launch.
     *
     * IntelliJ can construct a command state on the EDT.  Runtime discovery
     * starts `wsl.exe` and waits for its output, which is forbidden there.
     * Startup discovery fills the persisted Sage path before normal use; if it
     * is still empty, the direct launch fails quickly instead of probing.
     */
    internal fun usesConfiguredWslRuntime(settings: SageRunSettings.State): Boolean =
        settings.executionMode == ExecutionMode.WSL.name &&
            sageSdkName.isNullOrBlank()

    fun resolveSageExecutables(): RuntimeOperationResult<ResolvedRuntimeExecutables> {
        val configured = sageSdkName?.trim().orEmpty()
        val sdkResult = resolveSageSdk()
        if (sdkResult.succeeded) {
            val sdk = sdkResult.value!!
            if (sdk.sdkType === SageRuntimeSdkType.getInstance()) {
                return SageRuntimeSdkService.getInstance().resolveSdkExecutables(sdk)
            }
            val settings = SageRunSettings.getInstance().getState()
            if (configured.isEmpty()) {
                return when (settings.executionMode) {
                    ExecutionMode.NATIVE.name -> SageRuntimeService.getInstance().resolveNativeExecutables(settings.nativeSageExecutable)
                    ExecutionMode.WSL.name -> SageRuntimeService.getInstance().resolveWslExecutables(
                        distribution = settings.wslDistribution,
                        condaEnvironment = settings.wslCondaEnvironment,
                        condaExecutable = settings.wslCondaExecutable,
                        sageExecutable = settings.wslSageExecutable,
                    )
                    ExecutionMode.DOCKER.name -> SageRuntimeService.getInstance().resolveContainerExecutables(settings)
                    ExecutionMode.SSH.name -> SageRuntimeService.getInstance().resolveSshExecutables(settings)
                    else -> RuntimeOperationResult(
                        null,
                        listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_INVALID, "RUN_SDK_RESOLVE", "Unknown Sage execution mode: ${settings.executionMode}")),
                        false,
                    )
                }
            }
            return RuntimeOperationResult(
                null,
                listOf(
                    RuntimeDiagnostic(
                        RuntimeDiagnosticCode.RUNTIME_INVALID,
                        "RUN_SDK_RESOLVE",
                        "The selected project SDK is not a SageMath Runtime SDK",
                    ),
                ),
                false,
            )
        }
        val settings = SageRunSettings.getInstance().getState()
        if (configured.isEmpty()) {
            return when (settings.executionMode) {
                ExecutionMode.NATIVE.name -> SageRuntimeService.getInstance().resolveNativeExecutables(settings.nativeSageExecutable)
                ExecutionMode.WSL.name -> SageRuntimeService.getInstance().resolveWslExecutables(
                    distribution = settings.wslDistribution,
                    condaEnvironment = settings.wslCondaEnvironment,
                    condaExecutable = settings.wslCondaExecutable,
                    sageExecutable = settings.wslSageExecutable,
                )
                ExecutionMode.DOCKER.name -> SageRuntimeService.getInstance().resolveContainerExecutables(settings)
                else -> RuntimeOperationResult(
                    null,
                    listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_INVALID, "RUN_SDK_RESOLVE", "Unknown Sage execution mode: ${settings.executionMode}")),
                    false,
                )
            }
        }
        return RuntimeOperationResult(null, sdkResult.diagnostics, false)
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
        // IntelliJ invokes this method while recalculating run-configuration state
        // under a ReadAction. Runtime discovery launches external processes (notably
        // wsl.exe), so it must stay in the execution state rather than this callback.
        configurationValidationError(scriptPath, SageRunSettings.getInstance().getState())?.let {
            throw RuntimeConfigurationException(it)
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
