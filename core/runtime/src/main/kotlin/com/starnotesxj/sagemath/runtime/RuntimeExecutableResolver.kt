package com.starnotesxj.sagemath.runtime

/**
 * Target-visible Sage and bundled-Python executables for one verified runtime.
 *
 * The Python path is deliberately optional for legacy manifests. Callers that
 * require Python must handle RUNTIME_PYTHON_UNAVAILABLE instead of guessing a
 * filename or falling back to a separately installed interpreter.
 */
data class ResolvedRuntimeExecutables(
    val sage: String,
    val python: String?,
    val runtimeRoot: String?,
    val target: RuntimeTarget,
)

object RuntimeExecutableResolver {
    fun resolve(
        runtime: InstalledRuntime,
        target: RuntimeTarget,
        remoteRoot: String? = null,
    ): RuntimeOperationResult<ResolvedRuntimeExecutables> {
        RuntimeTargetCompatibility.diagnostic(runtime.id, target)?.let {
            return RuntimeOperationResult(null, listOf(it), false)
        }
        val manifest = runtime.manifest
            ?: return invalid(runtime, target, "Verified runtime manifest is missing")
        val pythonRelative = manifest.pythonExecutable
            ?: return RuntimeOperationResult(
                null,
                listOf(
                    RuntimeDiagnostic(
                        RuntimeDiagnosticCode.RUNTIME_PYTHON_UNAVAILABLE,
                        "RUNTIME_PYTHON_RESOLVE",
                        "This SageMath runtime predates bundled-Python metadata",
                        details = mapOf("runtimeId" to runtime.id.toString()),
                    ),
                ),
                false,
            )
        val pythonLocal = runtime.pythonExecutable
            ?: return invalid(runtime, target, "Declared bundled Python failed local verification", pythonRelative)

        return when (target) {
            RuntimeTarget.Native -> RuntimeOperationResult(
                ResolvedRuntimeExecutables(
                    sage = runtime.executable.toAbsolutePath().normalize().toString(),
                    python = pythonLocal.toAbsolutePath().normalize().toString(),
                    runtimeRoot = runtime.root.toAbsolutePath().normalize().toString(),
                    target = target,
                ),
            )

            is RuntimeTarget.Wsl,
            is RuntimeTarget.Docker,
            -> runCatching {
                val mapper = RuntimePathMapper()
                RuntimeOperationResult(
                    ResolvedRuntimeExecutables(
                        sage = mapper.toTarget(runtime.executable, target),
                        python = mapper.toTarget(pythonLocal, target),
                        runtimeRoot = mapper.toTarget(runtime.root, target),
                        target = target,
                    ),
                )
            }.getOrElse { error ->
                val diagnostic = (error as? RuntimePathMappingException)?.diagnostic
                    ?: RuntimeDiagnostic(RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED, "RUNTIME_PYTHON_RESOLVE", error.message ?: "Target path mapping failed")
                RuntimeOperationResult(null, listOf(diagnostic), false)
            }

            is RuntimeTarget.RemoteSsh -> {
                val root = (remoteRoot ?: target.runtimeRoot)?.trim()?.takeIf { it.isNotEmpty() }
                    ?: return RuntimeOperationResult(
                        null,
                        listOf(
                            RuntimeDiagnostic(
                                RuntimeDiagnosticCode.PATH_MAPPING_REQUIRED,
                                "RUNTIME_PYTHON_RESOLVE",
                                "Remote SageMath execution requires an explicit remote runtime root",
                            ),
                        ),
                        false,
                    )
                runCatching {
                    ResolvedRuntimeExecutables(
                        sage = joinRemote(root, manifest.executable),
                        python = joinRemote(root, pythonRelative),
                        runtimeRoot = normalizeRemoteRoot(root),
                        target = target,
                    )
                }.fold(
                    onSuccess = { RuntimeOperationResult(it) },
                    onFailure = { error ->
                        RuntimeOperationResult(
                            null,
                            listOf(
                                RuntimeDiagnostic(
                                    RuntimeDiagnosticCode.PATH_OUTSIDE_MAPPING,
                                    "RUNTIME_PYTHON_RESOLVE",
                                    error.message ?: "Remote runtime path is invalid",
                                ),
                            ),
                            false,
                        )
                    },
                )
            }
        }
    }

    private fun invalid(
        runtime: InstalledRuntime,
        target: RuntimeTarget,
        message: String,
        pythonRelative: String? = null,
    ): RuntimeOperationResult<ResolvedRuntimeExecutables> = RuntimeOperationResult(
        null,
        listOf(
            RuntimeDiagnostic(
                RuntimeDiagnosticCode.RUNTIME_INVALID,
                "RUNTIME_PYTHON_RESOLVE",
                message,
                details = buildMap {
                    put("runtimeId", runtime.id.toString())
                    put("target", target.kindName())
                    pythonRelative?.let { put("pythonExecutable", it) }
                },
            ),
        ),
        false,
    )

    private fun joinRemote(root: String, relative: String): String {
        require(RuntimeArtifact.isSafeRelativePath(relative)) { "Runtime executable path is not safe: $relative" }
        return "${normalizeRemoteRoot(root)}/$relative"
    }

    private fun normalizeRemoteRoot(value: String): String {
        val normalized = value.trim().replace('\\', '/')
        require(normalized.startsWith('/')) { "Remote runtime root must be an absolute POSIX path" }
        require(!normalized.startsWith("//")) { "Remote runtime root must not use an ambiguous UNC prefix" }
        val components = normalized.split('/').drop(1)
        require(components.isNotEmpty() && components.none { it.isBlank() || it == "." || it == ".." }) {
            "Remote runtime root contains empty or traversal components"
        }
        return "/" + components.joinToString("/")
    }
}
