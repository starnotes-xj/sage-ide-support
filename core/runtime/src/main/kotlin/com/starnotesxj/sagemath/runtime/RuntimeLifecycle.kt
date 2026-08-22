package com.starnotesxj.sagemath.runtime

import java.nio.channels.FileChannel
import java.nio.file.AtomicMoveNotSupportedException
import java.nio.file.Files
import java.nio.file.LinkOption
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption
import java.time.Instant
import java.util.UUID

interface RuntimeLifecycle {
    fun listInstalled(): List<InstalledRuntime>
    fun current(): RuntimeOperationResult<InstalledRuntime>
    fun select(id: SageRuntimeId): RuntimeOperationResult<InstalledRuntime>
    fun remove(id: SageRuntimeId): RuntimeOperationResult<Unit>
    fun rollback(): RuntimeOperationResult<InstalledRuntime>
    fun find(id: SageRuntimeId): InstalledRuntime? = listInstalled().firstOrNull { it.id == id }
}

/**
 * Manages immutable runtime versions independently from the installer.
 * Selection only publishes a verified version name; it never moves files
 * into the current location and therefore remains recoverable after a crash.
 */
class FileRuntimeLifecycle(
    private val installRoot: Path,
    private val manifestVerifier: RuntimeManifestVerifier = FileRuntimeManifestVerifier(),
) : RuntimeLifecycle {
    private val root: Path = installRoot.toAbsolutePath().normalize()
    private val versionsRoot: Path = root.resolve("versions")
    private val currentPointer: Path = root.resolve("current")
    private val historyFile: Path = root.resolve(".current-history")

    override fun listInstalled(): List<InstalledRuntime> {
        if (Files.isSymbolicLink(root) || !Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) return emptyList()
        if (Files.isSymbolicLink(versionsRoot) || !Files.isDirectory(versionsRoot, LinkOption.NOFOLLOW_LINKS)) return emptyList()
        return runCatching {
            Files.list(versionsRoot).use { stream ->
                stream.toList()
                    .asSequence()
                    .filter { path ->
                        !path.fileName.toString().startsWith(".") &&
                            !Files.isSymbolicLink(path) &&
                            Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)
                    }
                    .mapNotNull { path -> readInstalled(path.fileName.toString()) }
                    .sortedByDescending { it.verifiedAt }
                    .toList()
            }
        }.getOrDefault(emptyList())
    }

    override fun current(): RuntimeOperationResult<InstalledRuntime> {
        if (!Files.exists(root, LinkOption.NOFOLLOW_LINKS) || !Files.isDirectory(root, LinkOption.NOFOLLOW_LINKS)) {
            return failure(RuntimeDiagnosticCode.CURRENT_POINTER_MISSING, "CURRENT_READ", "Runtime install root does not exist")
        }
        if (Files.isSymbolicLink(currentPointer) || !Files.isRegularFile(currentPointer, LinkOption.NOFOLLOW_LINKS)) {
            return if (Files.exists(currentPointer, LinkOption.NOFOLLOW_LINKS)) {
                failure(RuntimeDiagnosticCode.CURRENT_POINTER_CORRUPT, "CURRENT_READ", "Runtime current pointer is not a regular file")
            }
            else {
                failure(RuntimeDiagnosticCode.CURRENT_POINTER_MISSING, "CURRENT_READ", "Runtime current pointer is missing")
            }
        }
        val name = readPointer()
            ?: return failure(RuntimeDiagnosticCode.CURRENT_POINTER_CORRUPT, "CURRENT_READ", "Runtime current pointer contains an unsafe value")
        val installed = readInstalled(name)
            ?: return failure(RuntimeDiagnosticCode.CURRENT_RUNTIME_INVALID, "CURRENT_READ", "Runtime current pointer does not reference a verified installation")
        return RuntimeOperationResult(installed)
    }

    override fun select(id: SageRuntimeId): RuntimeOperationResult<InstalledRuntime> {
        val target = find(id)
            ?: return failure(RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED, "RUNTIME_SELECT", "Requested SageMath runtime is not installed", mapOf("runtimeId" to id.toString()))
        val existing = current()
        if (existing.succeeded && existing.value!!.id == id) {
            return RuntimeOperationResult(
                value = target,
                diagnostics = listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_ALREADY_CURRENT, "RUNTIME_SELECT", "Requested SageMath runtime is already current")),
            )
        }
        return try {
            if (existing.succeeded) appendHistory(readPointer()!!)
            publishCurrent(target.root.fileName.toString())
            RuntimeOperationResult(target)
        }
        catch (error: Exception) {
            failure(RuntimeDiagnosticCode.RUNTIME_SELECT_FAILED, "RUNTIME_SELECT", "Unable to select SageMath runtime", cause = error)
        }
    }

    override fun remove(id: SageRuntimeId): RuntimeOperationResult<Unit> {
        val target = find(id)
            ?: return failure(RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED, "RUNTIME_REMOVE", "Requested SageMath runtime is not installed")
        val existing = current()
        return try {
            if (existing.succeeded && existing.value!!.id == id) {
                val replacement = listInstalled().firstOrNull { it.id != id }
                    ?: return failure(RuntimeDiagnosticCode.RUNTIME_REMOVE_FAILED, "RUNTIME_REMOVE", "Cannot remove the only current SageMath runtime")
                val oldCurrentName = existing.value.root.fileName.toString()
                appendHistory(oldCurrentName)
                publishCurrent(replacement.root.fileName.toString())
            }
            deleteInstalled(target)
            RuntimeOperationResult(Unit)
        }
        catch (error: Exception) {
            failure(RuntimeDiagnosticCode.RUNTIME_REMOVE_FAILED, "RUNTIME_REMOVE", "Unable to remove SageMath runtime", cause = error)
        }
    }

    override fun rollback(): RuntimeOperationResult<InstalledRuntime> {
        val currentName = readPointer()
        val candidates = historyNames().asSequence()
            .mapNotNull(::readInstalled)
            .filter { it.root.fileName.toString() != currentName }
            .plus(listInstalled().asSequence().filter { it.root.fileName.toString() != currentName })
            .distinctBy { it.id }
            .toList()
        val target = candidates.firstOrNull()
            ?: return failure(RuntimeDiagnosticCode.RUNTIME_ROLLBACK_UNAVAILABLE, "RUNTIME_ROLLBACK", "No verified previous SageMath runtime is available")
        return try {
            currentName?.takeIf { it != target.root.fileName.toString() }?.let(::appendHistory)
            publishCurrent(target.root.fileName.toString())
            RuntimeOperationResult(target)
        }
        catch (error: Exception) {
            failure(RuntimeDiagnosticCode.RUNTIME_ROLLBACK_UNAVAILABLE, "RUNTIME_ROLLBACK", "Unable to roll back SageMath runtime", cause = error)
        }
    }

    private fun readInstalled(name: String): InstalledRuntime? {
        if (name.isBlank() || name.length > 128 || !RuntimeArtifact.isSafeRelativePath(name) || name.contains('/') || name.contains('\\')) return null
        val runtimeRoot = versionsRoot.resolve(name).normalize()
        if (!runtimeRoot.startsWith(versionsRoot) || Files.isSymbolicLink(runtimeRoot) || !Files.isDirectory(runtimeRoot, LinkOption.NOFOLLOW_LINKS)) return null
        val marker = versionsRoot.resolve(".$name.meta")
        if (Files.isSymbolicLink(marker) || !Files.isRegularFile(marker, LinkOption.NOFOLLOW_LINKS)) return null
        val manifest = runCatching {
            val size = Files.size(marker)
            require(size in 1..RuntimeManifestCodec.MAX_ENCODED_BYTES)
            RuntimeManifestCodec.decode(Files.readAllBytes(marker))
        }.getOrNull() ?: return null
        if (!manifest.runtimeId.isValidInstalledDirectoryName(name)) return null
        val executable = runtimeRoot.resolve(manifest.executable).normalize()
        if (!executable.startsWith(runtimeRoot) || Files.isSymbolicLink(executable) || !Files.isRegularFile(executable, LinkOption.NOFOLLOW_LINKS)) return null
        if (!manifestVerifier.verify(runtimeRoot, manifest).valid) return null
        return InstalledRuntime(manifest.runtimeId, runtimeRoot, executable, Files.getLastModifiedTime(runtimeRoot).toInstant(), manifest)
    }

    private fun readPointer(): String? {
        if (Files.isSymbolicLink(currentPointer) || !Files.isRegularFile(currentPointer, LinkOption.NOFOLLOW_LINKS)) return null
        return runCatching {
            require(Files.size(currentPointer) in 1..128)
            Files.readString(currentPointer).trim().takeIf {
                it.isNotEmpty() && RuntimeArtifact.isSafeRelativePath(it) && !it.contains('/') && !it.contains('\\')
            }
        }.getOrNull()
    }

    private fun historyNames(): List<String> {
        if (Files.isSymbolicLink(historyFile) || !Files.isRegularFile(historyFile, LinkOption.NOFOLLOW_LINKS)) return emptyList()
        return runCatching {
            Files.readAllLines(historyFile).asReversed().asSequence()
                .map(String::trim)
                .filter { it.isNotEmpty() && it.length <= 128 && RuntimeArtifact.isSafeRelativePath(it) && !it.contains('/') && !it.contains('\\') }
                .distinct()
                .take(MAX_HISTORY_ENTRIES)
                .toList()
        }.getOrDefault(emptyList())
    }

    private fun appendHistory(name: String) {
        val names = (historyNames().asReversed() + name).distinct().takeLast(MAX_HISTORY_ENTRIES)
        atomicWrite(historyFile, names.joinToString("\n") + "\n")
    }

    private fun publishCurrent(name: String) {
        require(RuntimeArtifact.isSafeRelativePath(name) && !name.contains('/') && !name.contains('\\'))
        ensureDirectoryChainIsNotSymbolic(root)
        if (Files.isSymbolicLink(currentPointer)) {
            throw IllegalStateException("Runtime current pointer path is symbolic")
        }
        Files.createDirectories(root)
        atomicWrite(currentPointer, name)
    }

    private fun atomicWrite(destination: Path, content: String) {
        require(destination.toAbsolutePath().normalize().parent == root) { "Runtime pointer must be directly under install root" }
        ensureDirectoryChainIsNotSymbolic(root)
        val temporary = root.resolve(".${destination.fileName}.${UUID.randomUUID()}.tmp")
        Files.writeString(temporary, content, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)
        try {
            FileChannel.open(temporary, StandardOpenOption.WRITE).use { it.force(true) }
            try {
                Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            }
            catch (_: AtomicMoveNotSupportedException) {
                Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING)
            }
        }
        finally {
            Files.deleteIfExists(temporary)
        }
    }

    private fun deleteInstalled(runtime: InstalledRuntime) {
        ensureDirectoryChainIsNotSymbolic(versionsRoot)
        val normalized = runtime.root.toAbsolutePath().normalize()
        require(normalized.parent == versionsRoot)
        if (Files.isSymbolicLink(normalized)) error("Runtime installation is symbolic")
        Files.walk(normalized).use { stream -> stream.sorted(Comparator.reverseOrder()).forEach(Files::deleteIfExists) }
        Files.deleteIfExists(versionsRoot.resolve(".${normalized.fileName}.meta"))
    }

    private fun ensureDirectoryChainIsNotSymbolic(path: Path) {
        val absolute = path.toAbsolutePath().normalize()
        var current = absolute.root ?: error("Runtime path must have a root")
        for (part in absolute) {
            current = current.resolve(part.toString())
            if (Files.isSymbolicLink(current)) error("Runtime path contains a symbolic link: $current")
        }
    }

    private fun <T> failure(
        code: RuntimeDiagnosticCode,
        stage: String,
        message: String,
        details: Map<String, String> = emptyMap(),
        cause: Throwable? = null,
    ): RuntimeOperationResult<T> = RuntimeOperationResult(
        value = null,
        diagnostics = listOf(RuntimeDiagnostic(code, stage, message, details, cause?.javaClass?.name)),
        succeeded = false,
    )

    companion object {
        private const val MAX_HISTORY_ENTRIES = 32
    }
}

/** Settings/project SDK state stays in the runtime module until IntelliJ adapters are approved. */
data class RuntimeSdkBinding(
    val runtimeId: SageRuntimeId,
    val target: RuntimeTarget,
)

interface RuntimeSdkStore {
    fun settings(): RuntimeSdkBinding?
    fun project(projectId: String): RuntimeSdkBinding?
    fun setSettings(binding: RuntimeSdkBinding)
    fun setProject(projectId: String, binding: RuntimeSdkBinding)
}

class InMemoryRuntimeSdkStore : RuntimeSdkStore {
    private var settingsBinding: RuntimeSdkBinding? = null
    private val projectBindings = linkedMapOf<String, RuntimeSdkBinding>()
    override fun settings(): RuntimeSdkBinding? = settingsBinding
    override fun project(projectId: String): RuntimeSdkBinding? = projectBindings[projectId]
    override fun setSettings(binding: RuntimeSdkBinding) { settingsBinding = binding }
    override fun setProject(projectId: String, binding: RuntimeSdkBinding) { projectBindings[projectId] = binding }
}

class RuntimeSdkAdapter(
    private val lifecycle: RuntimeLifecycle,
    private val store: RuntimeSdkStore,
) {
    fun selectSettings(id: SageRuntimeId, target: RuntimeTarget): RuntimeOperationResult<RuntimeSdkBinding> {
        val selected = lifecycle.select(id)
        if (!selected.succeeded) return RuntimeOperationResult(null, selected.diagnostics, false)
        val binding = RuntimeSdkBinding(id, target)
        store.setSettings(binding)
        return RuntimeOperationResult(binding, selected.diagnostics)
    }

    fun selectProject(projectId: String, id: SageRuntimeId, target: RuntimeTarget): RuntimeOperationResult<RuntimeSdkBinding> {
        val installed = lifecycle.find(id)
            ?: return RuntimeOperationResult(
                null,
                listOf(RuntimeDiagnostic(RuntimeDiagnosticCode.RUNTIME_NOT_INSTALLED, "SDK_PROJECT_SELECT", "Project SDK runtime is not installed")),
                false,
            )
        val binding = RuntimeSdkBinding(installed.id, target)
        store.setProject(projectId, binding)
        return RuntimeOperationResult(binding)
    }

    fun effective(projectId: String): RuntimeSdkBinding? = store.project(projectId) ?: store.settings()
}
