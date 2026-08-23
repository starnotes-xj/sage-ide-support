package com.starnotesxj.sageide.runtime

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.projectRoots.ProjectJdkTable
import com.intellij.openapi.projectRoots.Sdk
import com.intellij.openapi.projectRoots.SdkModel
import com.intellij.openapi.projectRoots.SdkModificator
import com.starnotesxj.sagemath.runtime.InstalledRuntime
import com.starnotesxj.sagemath.runtime.RuntimeDiagnostic
import com.starnotesxj.sagemath.runtime.ResolvedRuntimeExecutables
import com.starnotesxj.sagemath.runtime.RuntimeDiagnosticCode
import com.starnotesxj.sagemath.runtime.RuntimeExecutableResolver
import com.starnotesxj.sagemath.runtime.InstallationCancellation
import com.starnotesxj.sagemath.runtime.InstallResult
import com.starnotesxj.sagemath.runtime.JdkHttpRuntimeDownloader
import com.starnotesxj.sagemath.runtime.RuntimeCatalogLoadResult
import com.starnotesxj.sagemath.runtime.RuntimeCatalogSource
import com.starnotesxj.sagemath.runtime.RuntimeControl
import com.starnotesxj.sagemath.runtime.RuntimeManifest
import com.starnotesxj.sagemath.runtime.RuntimeLifecycle
import com.starnotesxj.sagemath.runtime.RuntimeOperationResult
import com.starnotesxj.sagemath.runtime.RuntimeSdkBinding
import com.starnotesxj.sagemath.runtime.RuntimeQuery
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import com.starnotesxj.sagemath.runtime.RuntimeTargetCompatibility
import com.starnotesxj.sagemath.runtime.SageRuntimeId
import java.nio.file.Path

/** Bridges the verified Runtime Manager model to IntelliJ's non-extendable Sdk objects. */
class SageRuntimeSdkAdapter(
    private val lifecycle: RuntimeLifecycle,
) {
    fun createSdk(
        sdkModel: SdkModel,
        runtime: InstalledRuntime,
        target: RuntimeTarget,
    ): RuntimeOperationResult<Sdk> {
        val validation = validate(runtime.id, target)
        if (!validation.succeeded) return RuntimeOperationResult(null, validation.diagnostics, false)
        if (runtime.manifest?.pythonExecutable == null) {
            return RuntimeOperationResult(
                null,
                listOf(
                    RuntimeDiagnostic(
                        RuntimeDiagnosticCode.RUNTIME_PYTHON_UNAVAILABLE,
                        "SDK_CREATE",
                        "The selected SageMath runtime does not expose a bundled Python interpreter",
                    ),
                ),
                false,
            )
        }
        val executableResolution = RuntimeExecutableResolver.resolve(runtime, target)
        if (!executableResolution.succeeded) {
            return RuntimeOperationResult(null, executableResolution.diagnostics, false)
        }
        val binding = RuntimeSdkBinding(runtime.id, target)
        val sdk = ProjectJdkTable.getInstance().createSdk(SageRuntimeSdkDisplay.sdkName(binding), SageRuntimeSdkType.getInstance())
        val modificator = sdk.sdkModificator
        modificator.setHomePath(runtime.root.toAbsolutePath().normalize().toString())
        modificator.setVersionString(runtime.manifest?.sageVersion ?: runtime.id.version)
        // The managed Sage SDK remains independent from PyCharm's strict
        // Python SDK identity. Python-dependent consumers use the resolved
        // manifest path through SageRuntimeSdkService instead of a fake SDK.
        modificator.setSdkAdditionalData(SageRuntimeSdkAdditionalData(runtime.id, target))
        commit(modificator)
        sdkModel.addSdk(sdk)
        return RuntimeOperationResult(sdk)
    }

    /** Resolves the Python interpreter shipped by the selected SageMath runtime. */
    fun bundledExecutables(
        runtime: InstalledRuntime,
        target: RuntimeTarget,
        remoteRoot: String? = null,
    ): RuntimeOperationResult<ResolvedRuntimeExecutables> =
        RuntimeExecutableResolver.resolve(runtime, target, remoteRoot)

    fun bundledPython(
        runtime: InstalledRuntime,
        target: RuntimeTarget,
        remoteRoot: String? = null,
    ): RuntimeOperationResult<String> = bundledExecutables(runtime, target, remoteRoot).let { result ->
        val python = result.value?.python
        if (result.succeeded && python != null) RuntimeOperationResult(python, result.diagnostics)
        else if (!result.succeeded) RuntimeOperationResult(null, result.diagnostics, false)
        else RuntimeOperationResult(
            null,
            listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_PYTHON_UNAVAILABLE, "SDK_PYTHON", "Bundled SageMath Python is unavailable")),
            false,
        )
    }

    fun resolveSdk(sdk: Sdk, remoteRoot: String? = null): RuntimeOperationResult<ResolvedRuntimeExecutables> {
        val validation = validate(sdk)
        if (!validation.succeeded) return RuntimeOperationResult(null, validation.diagnostics, false)
        val binding = validation.value!!
        val installed = validate(binding.runtimeId, binding.target)
        if (!installed.succeeded) return RuntimeOperationResult(null, installed.diagnostics, false)
        return RuntimeExecutableResolver.resolve(installed.value!!, binding.target, remoteRoot)
    }

    fun validate(sdk: Sdk): RuntimeOperationResult<RuntimeSdkBinding> {
        if (sdk.sdkType !== SageRuntimeSdkType.getInstance()) {
            return invalid(
                "SDK_VALIDATE",
                "The selected SDK is not a SageMath Runtime SDK",
                mapOf("sdkType" to sdk.sdkType.name),
            )
        }
        val data = sdk.getSdkAdditionalData() as? SageRuntimeSdkAdditionalData
            ?: return invalid("SDK_VALIDATE", "SageMath SDK metadata is missing")
        val validation = validate(data.runtimeId, data.target)
        if (!validation.succeeded) return RuntimeOperationResult(null, validation.diagnostics, false)
        val installed = validation.value!!
        val home = sdk.homePath?.let { Path.of(it).toAbsolutePath().normalize() }
        if (home == null || home != installed.root.toAbsolutePath().normalize()) {
            return invalid(
                "SDK_VALIDATE",
                "SageMath SDK home does not match its verified runtime installation",
                mapOf("expectedHome" to installed.root.toString()),
            )
        }
        return RuntimeOperationResult(data.binding())
    }

    fun presentation(sdk: Sdk): SageRuntimeSdkPresentation {
        val data = sdk.getSdkAdditionalData() as? SageRuntimeSdkAdditionalData
            ?: return SageRuntimeSdkPresentation(
                sdkName = sdk.name,
                runtimeLabel = "Unknown SageMath runtime",
                targetLabel = "Unknown target",
                state = SageRuntimeSdkState.INVALID,
                diagnostic = "SageMath SDK metadata is missing",
            )
        val validation = validate(data.runtimeId, data.target)
        return presentationFor(sdk.name, data.binding(), validation.diagnostics)
    }

    fun validate(id: SageRuntimeId, target: RuntimeTarget): RuntimeOperationResult<InstalledRuntime> {
        val targetDiagnostic = RuntimeTargetCompatibility.diagnostic(id, target)
        if (targetDiagnostic != null) return RuntimeOperationResult(null, listOf(targetDiagnostic), false)
        val result = lifecycle.validate(id)
        if (result.succeeded) return result
        val diagnostics = result.diagnostics.map { diagnostic ->
            if (diagnostic.code == RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED && lifecycle.listInstalled().any { it.id == id }) {
                diagnostic.copy(
                    code = RuntimeDiagnosticCode.RUNTIME_INVALID,
                    message = "SageMath runtime installation is present but failed verification",
                )
            }
            else diagnostic
        }
        return RuntimeOperationResult(null, diagnostics, false)
    }

    fun selectSettings(binding: RuntimeSdkBinding): RuntimeOperationResult<RuntimeSdkBinding> =
        validate(binding.runtimeId, binding.target).let { result ->
            if (!result.succeeded) RuntimeOperationResult(null, result.diagnostics, false)
            else RuntimeOperationResult(binding)
        }

    private fun commit(modificator: SdkModificator) {
        val application = ApplicationManager.getApplication()
        if (application.isWriteAccessAllowed) {
            modificator.commitChanges()
        }
        else {
            application.runWriteAction { modificator.commitChanges() }
        }
    }

    private fun <T> invalid(
        stage: String,
        message: String,
        details: Map<String, String> = emptyMap(),
    ): RuntimeOperationResult<T> = RuntimeOperationResult(
        null,
        listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_INVALID, stage, message, details)),
        false,
    )
}

@Service(Service.Level.APP)
class SageRuntimeManagerService : Disposable {
    val installRoot: Path = Path.of(
        System.getProperty("user.home", "."),
        ".sage-math-ctf-ide",
        "runtimes",
    ).toAbsolutePath().normalize()
    val lifecycle: RuntimeLifecycle = com.starnotesxj.sagemath.runtime.FileRuntimeLifecycle(installRoot)
    val sdkAdapter: SageRuntimeSdkAdapter = SageRuntimeSdkAdapter(lifecycle)

    @Volatile
    private var lastCatalog: RuntimeCatalogLoadResult? = null

    fun installedRuntimes(): List<InstalledRuntime> = lifecycle.listInstalled()

    fun currentRuntime(): RuntimeOperationResult<InstalledRuntime> = lifecycle.current()

    fun validateRuntime(id: SageRuntimeId): RuntimeOperationResult<InstalledRuntime> = lifecycle.validate(id)

    fun selectRuntime(id: SageRuntimeId): RuntimeOperationResult<InstalledRuntime> = lifecycle.select(id)

    fun removeRuntime(id: SageRuntimeId): RuntimeOperationResult<Unit> = lifecycle.remove(id)

    fun rollbackRuntime(): RuntimeOperationResult<InstalledRuntime> = lifecycle.rollback()

    /**
     * Loads a signed catalog through the supplied source and caches only
     * verifier-approved bytes. The loader is retained so catalog refresh and
     * install operations share one service-owned cache policy and install root.
     */
    fun loadCatalog(
        primary: java.net.URI,
        mirrors: List<java.net.URI> = emptyList(),
        source: RuntimeCatalogSource,
        cachePath: Path = installRoot.resolve("catalog.cache"),
        control: RuntimeControl = RuntimeControl(),
    ): RuntimeCatalogLoadResult {
        val loader = com.starnotesxj.sagemath.runtime.SignedRuntimeCatalogLoader(source, cachePath = cachePath)
        return loader.load(primary, mirrors, control).also { lastCatalog = it }
    }

    fun lastCatalogLoad(): RuntimeCatalogLoadResult? = lastCatalog

    fun availableRuntimes(query: RuntimeQuery = RuntimeQuery()): List<com.starnotesxj.sagemath.runtime.RuntimeArtifact> =
        lastCatalog?.trustedCatalog?.list(query).orEmpty()

    /** Installs only an artifact present in the last verified catalog load. */
    fun installRuntime(
        catalog: com.starnotesxj.sagemath.runtime.VerifiedRuntimeCatalog,
        id: SageRuntimeId,
        manifest: RuntimeManifest,
        downloader: com.starnotesxj.sagemath.runtime.RuntimeDownloader = JdkHttpRuntimeDownloader(),
        progress: com.starnotesxj.sagemath.runtime.DownloadProgressListener = com.starnotesxj.sagemath.runtime.NoopDownloadProgress,
        cancellation: InstallationCancellation = com.starnotesxj.sagemath.runtime.NeverCancelled,
        replaceExisting: Boolean = false,
        control: RuntimeControl = RuntimeControl(),
    ): InstallResult {
        require(lastCatalog?.trustedCatalog === catalog) {
            "Runtime installation requires the catalog most recently verified by SageRuntimeManagerService"
        }
        return com.starnotesxj.sagemath.runtime.VerifiedRuntimeInstaller(
            com.starnotesxj.sagemath.runtime.ZipRuntimeInstaller(downloader),
        ).install(
            catalog = catalog,
            id = id,
            installRoot = installRoot,
            manifest = manifest,
            progress = progress,
            cancellation = cancellation,
            replaceExisting = replaceExisting,
            control = control,
        )
    }

    override fun dispose() {
        lastCatalog = null
    }

    companion object {
        @JvmStatic
        fun getInstance(): SageRuntimeManagerService =
            ApplicationManager.getApplication().getService(SageRuntimeManagerService::class.java)
    }
}

/** Compatibility facade; the Runtime Manager service owns the canonical lifecycle and install root. */
@Service(Service.Level.APP)
class SageRuntimeSdkService : Disposable {
    private val manager: SageRuntimeManagerService
        get() = SageRuntimeManagerService.getInstance()
    val sdkAdapter: SageRuntimeSdkAdapter
        get() = manager.sdkAdapter

    fun installedRuntimes(): List<InstalledRuntime> = manager.installedRuntimes()

    fun availableRuntimes(query: RuntimeQuery = RuntimeQuery()): List<com.starnotesxj.sagemath.runtime.RuntimeArtifact> = manager.availableRuntimes(query)

    fun currentRuntime(): RuntimeOperationResult<InstalledRuntime> = manager.currentRuntime()

    fun validateRuntime(id: SageRuntimeId): RuntimeOperationResult<InstalledRuntime> = manager.validateRuntime(id)

    fun selectRuntime(id: SageRuntimeId): RuntimeOperationResult<InstalledRuntime> = manager.selectRuntime(id)

    fun removeRuntime(id: SageRuntimeId): RuntimeOperationResult<Unit> = manager.removeRuntime(id)

    fun rollbackRuntime(): RuntimeOperationResult<InstalledRuntime> = manager.rollbackRuntime()

    fun loadCatalog(
        primary: java.net.URI,
        mirrors: List<java.net.URI> = emptyList(),
        source: RuntimeCatalogSource,
        cachePath: Path = manager.installRoot.resolve("catalog.cache"),
        control: RuntimeControl = RuntimeControl(),
    ): RuntimeCatalogLoadResult = manager.loadCatalog(primary, mirrors, source, cachePath, control)

    fun installRuntime(
        catalog: com.starnotesxj.sagemath.runtime.VerifiedRuntimeCatalog,
        id: SageRuntimeId,
        manifest: RuntimeManifest,
        downloader: com.starnotesxj.sagemath.runtime.RuntimeDownloader = JdkHttpRuntimeDownloader(),
        progress: com.starnotesxj.sagemath.runtime.DownloadProgressListener = com.starnotesxj.sagemath.runtime.NoopDownloadProgress,
        cancellation: InstallationCancellation = com.starnotesxj.sagemath.runtime.NeverCancelled,
        replaceExisting: Boolean = false,
        control: RuntimeControl = RuntimeControl(),
    ): InstallResult = manager.installRuntime(catalog, id, manifest, downloader, progress, cancellation, replaceExisting, control)

    fun validate(id: SageRuntimeId, target: RuntimeTarget): RuntimeOperationResult<InstalledRuntime> =
        sdkAdapter.validate(id, target)

    fun createSdk(
        sdkModel: SdkModel,
        runtime: InstalledRuntime,
        target: RuntimeTarget,
    ): RuntimeOperationResult<Sdk> = sdkAdapter.createSdk(sdkModel, runtime, target)

    fun bundledExecutables(
        runtime: InstalledRuntime,
        target: RuntimeTarget,
        remoteRoot: String? = null,
    ): RuntimeOperationResult<ResolvedRuntimeExecutables> =
        sdkAdapter.bundledExecutables(runtime, target, remoteRoot)

    fun resolveSdkExecutables(
        sdk: Sdk,
        remoteRoot: String? = null,
    ): RuntimeOperationResult<ResolvedRuntimeExecutables> = sdkAdapter.resolveSdk(sdk, remoteRoot)

    fun currentExecutables(
        target: RuntimeTarget,
        remoteRoot: String? = null,
    ): RuntimeOperationResult<ResolvedRuntimeExecutables> {
        val current = manager.lifecycle.current()
        val runtime = current.value
            ?: return RuntimeOperationResult(null, current.diagnostics, false)
        return sdkAdapter.bundledExecutables(runtime, target, remoteRoot)
    }

    override fun dispose() = Unit

    companion object {
        @JvmStatic
        fun getInstance(): SageRuntimeSdkService =
            ApplicationManager.getApplication().getService(SageRuntimeSdkService::class.java)
    }
}
