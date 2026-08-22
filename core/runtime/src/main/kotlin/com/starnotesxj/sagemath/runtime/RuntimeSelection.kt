package com.starnotesxj.sagemath.runtime

/**
 * Installs only artifacts selected from a previously verified catalog. The
 * trusted capability cannot be fabricated by callers because its constructor
 * is private and it is returned only by RuntimeCatalogSignatureVerifier.
 */
class VerifiedRuntimeInstaller(
    private val installer: RuntimeInstaller,
) {
    fun install(
        catalog: VerifiedRuntimeCatalog,
        id: SageRuntimeId,
        installRoot: java.nio.file.Path,
        manifest: RuntimeManifest,
        progress: DownloadProgressListener = NoopDownloadProgress,
        cancellation: InstallationCancellation = NeverCancelled,
        replaceExisting: Boolean = false,
        control: RuntimeControl = RuntimeControl(),
    ): InstallResult {
        val artifact = catalog.resolve(id)
            ?: return InstallResult.Failed(
                stage = "CATALOG_RUNTIME_NOT_FOUND",
                cause = RuntimeInstallException("CATALOG_RUNTIME_NOT_FOUND", "Verified catalog does not contain the requested runtime"),
                cleanupPerformed = true,
            )
        val request = RuntimeInstallRequest(
            artifact = artifact,
            installRoot = installRoot,
            manifest = manifest,
            progress = progress,
            cancellation = cancellation,
            replaceExisting = replaceExisting,
            control = control,
        )
        return installer.install(request)
    }
}
