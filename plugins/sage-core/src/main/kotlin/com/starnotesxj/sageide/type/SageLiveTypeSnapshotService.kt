package com.starnotesxj.sageide.type

import com.intellij.codeInsight.daemon.DaemonCodeAnalyzer
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiErrorElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyStatement
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.PyClassTypeImpl
import com.jetbrains.python.psi.types.PyType
import com.starnotesxj.sageide.run.SageRunSettings
import com.starnotesxj.sageide.run.SageRuntimeProbeHandle
import com.starnotesxj.sageide.run.SageRuntimeService
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sagemath.runtime.RuntimeExecutionStatus
import com.starnotesxj.sagemath.runtime.RuntimeTarget
import com.starnotesxj.sagemath.runtime.SageLiveTypeWorker
import com.starnotesxj.sagemath.runtime.SageLiveTypeWorkerQuery
import com.starnotesxj.sagemath.runtime.SageObservedType
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.time.Duration
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * Per-project cache of concrete Sage types observed by executing a bounded
 * prefix of the current unsaved document in a separate process.
 *
 * Results are keyed by the document prefix digest and never affect the global
 * Sage API index.  A static contract remains the only answer until the exact
 * current snapshot returns successfully.  The feature is opt-in because it
 * executes the user's source; an independent process prevents IDE state from
 * being contaminated but is not a security sandbox.
 */
@Service(Service.Level.PROJECT)
class SageLiveTypeSnapshotService(private val project: Project) : Disposable {
    private val completed = ConcurrentHashMap<SnapshotKey, Map<String, SageObservedType>>()
    private val inFlight = ConcurrentHashMap.newKeySet<SnapshotKey>()
    private val scheduled = ConcurrentHashMap<SnapshotKey, ScheduledFuture<*>>()
    private val active = ConcurrentHashMap<SnapshotKey, SageRuntimeProbeHandle<*>>()
    private val workerLock = Any()
    private var workerRuntime: ConfiguredRuntime? = null
    private var worker: SageLiveTypeWorker? = null
    private val debounceExecutor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "sage-live-type-snapshot").apply { isDaemon = true }
    }

    fun typeForReference(reference: PyReferenceExpression): PyType? {
        if (PsiTreeUtil.getParentOfType(reference, PyFunction::class.java) != null) return null
        val name = reference.referencedName ?: return null
        return typeFor(reference, name, includeContainingStatement = false)
    }

    fun typeForTarget(target: PyTargetExpression): PyType? {
        if (target.qualifier != null || PsiTreeUtil.getParentOfType(target, PyFunction::class.java) != null) return null
        val name = target.name ?: return null
        return typeFor(target, name, includeContainingStatement = true)
    }

    /**
     * Resolves the concrete result of a call that the static contract cannot
     * prove.  The current statement is not re-executed: the worker receives
     * the prefix before that statement followed by a synthetic assignment of
     * the call expression.  This keeps side effects bounded to the call being
     * inspected and lets calls such as ``P.log(G)`` participate in the same
     * runtime cache as assignment targets.
     */
    fun typeForCall(call: PyCallExpression): PyType? {
        if (PsiTreeUtil.getParentOfType(call, PyFunction::class.java) != null) return null
        val request = callSnapshotRequest(call) ?: return null
        val name = LIVE_RESULT_NAME
        val observed = completed[request.key]?.get(name)
        if (observed != null) return SageObservedTypeResolver.resolve(project, observed)
        schedule(request)
        return null
    }

    private fun typeFor(anchor: com.intellij.psi.PsiElement, name: String, includeContainingStatement: Boolean): PyType? {
        if (!isSafeIdentifier(name) || !SageRunSettings.getInstance().getState().liveTypeProbingEnabled) return null
        val request = snapshotRequest(anchor, name, includeContainingStatement) ?: return null
        val observed = completed[request.key]?.get(name)
        if (observed != null) return SageObservedTypeResolver.resolve(project, observed)
        schedule(request)
        return null
    }

    private fun snapshotRequest(
        anchor: com.intellij.psi.PsiElement,
        requestedName: String,
        includeContainingStatement: Boolean,
    ): SnapshotRequest? {
        val file = anchor.containingFile as? PyFile ?: return null
        if (!SageFileUtils.isSageFile(file) || SageStubIndex.isSageStubFile(file)) return null
        val virtualFile = file.virtualFile ?: return null
        val statement = PsiTreeUtil.getParentOfType(anchor, PyStatement::class.java) ?: return null
        val cutoff = if (includeContainingStatement) statement.textRange.endOffset else statement.textRange.startOffset
        if (cutoff <= 0) return null
        if (PsiTreeUtil.collectElementsOfType(file, PsiErrorElement::class.java)
                .any { it.textRange.startOffset < cutoff }) return null
        val fullText = file.text
        if (cutoff > fullText.length) return null
        val source = fullText.substring(0, cutoff)
        if (source.toByteArray(StandardCharsets.UTF_8).size > MAX_SOURCE_BYTES) return null
        val requestedNames = collectSnapshotNames(file, cutoff) + requestedName
        val runtime = configuredRuntime() ?: return null
        return SnapshotRequest(
            SnapshotKey(virtualFile.url, sha256(source), runtime.key),
            source,
            requestedNames,
            runtime,
            virtualFile.name,
            virtualFile,
        )
    }

    private fun callSnapshotRequest(call: PyCallExpression): SnapshotRequest? {
        val file = call.containingFile as? PyFile ?: return null
        if (!SageFileUtils.isSageFile(file) || SageStubIndex.isSageStubFile(file)) return null
        if (!SageRunSettings.getInstance().getState().liveTypeProbingEnabled) return null
        if (PsiTreeUtil.collectElementsOfType(call, PsiErrorElement::class.java).isNotEmpty()) return null
        val virtualFile = file.virtualFile ?: return null
        val statement = PsiTreeUtil.getParentOfType(call, PyStatement::class.java) ?: return null
        // A synthetic assignment cannot preserve whether a nested call was
        // reached through an if/loop/try branch.  Top-level expression
        // statements are the only calls whose control flow is unchanged by
        // the transformation; assignments in compound statements are still
        // handled by the normal prefix snapshot path.
        if (statement.parent !is PyFile) return null
        val cutoff = statement.textRange.startOffset
        if (cutoff <= 0 || cutoff > file.textLength) return null
        if (PsiTreeUtil.collectElementsOfType(file, PsiErrorElement::class.java)
                .any { it.textRange.startOffset < cutoff }) return null
        val prefix = file.text.substring(0, cutoff)
        val source = buildString {
            append(prefix)
            if (!endsWith("\n")) append('\n')
            append(LIVE_RESULT_NAME).append(" = ").append(call.text).append('\n')
        }
        if (source.toByteArray(StandardCharsets.UTF_8).size > MAX_SOURCE_BYTES) return null
        val runtime = configuredRuntime() ?: return null
        return SnapshotRequest(
            SnapshotKey(virtualFile.url, sha256(source), runtime.key),
            source,
            collectSnapshotNames(file, cutoff) + LIVE_RESULT_NAME,
            runtime,
            virtualFile.name,
            virtualFile,
        )
    }

    private fun collectSnapshotNames(file: PyFile, cutoff: Int): Set<String> =
        PsiTreeUtil.collectElementsOfType(file, PyTargetExpression::class.java)
            .asSequence()
            .filter { it.qualifier == null && PsiTreeUtil.getParentOfType(it, PyFunction::class.java) == null }
            .filter { target ->
                val assignment = PsiTreeUtil.getParentOfType(target, PyAssignmentStatement::class.java)
                assignment != null && assignment.textRange.endOffset <= cutoff
            }
            .mapNotNull(PyTargetExpression::getName)
            .filter(::isSafeIdentifier)
            .toSet()

    private fun configuredRuntime(): ConfiguredRuntime? {
        val settings = SageRunSettings.getInstance().getState()
        return when (settings.executionMode) {
            "NATIVE" -> settings.nativeSageExecutable.trim().takeIf(String::isNotEmpty)
                ?.let { ConfiguredRuntime(RuntimeTarget.Native, it) }
            "WSL" -> settings.wslSageExecutable.trim().takeIf(String::isNotEmpty)
                ?.let { ConfiguredRuntime(RuntimeTarget.Wsl(settings.wslDistribution.trim()), it) }
            else -> null
        }
    }

    private fun schedule(request: SnapshotRequest) {
        cancelStaleSnapshots(request.key)
        if (!inFlight.add(request.key)) return
        scheduled[request.key] = debounceExecutor.schedule({
            scheduled.remove(request.key)
            if (!inFlight.contains(request.key) || project.isDisposed) return@schedule
            val handle = SageRuntimeService.getInstance()
                .submit(LIVE_TYPE_PROBE_DEADLINE) { control ->
                    workerFor(request.runtime).probe(
                        SageLiveTypeWorkerQuery(
                            request.source,
                            request.requestedNames,
                            request.fileName,
                            control = control,
                        ),
                    )
                }
            active[request.key] = handle
            handle.future.whenComplete { result, error ->
                active.remove(request.key)
                inFlight.remove(request.key)
                if (error == null && result?.status == RuntimeExecutionStatus.SUCCESS) {
                    if (completed.size >= MAX_CACHED_SNAPSHOTS) completed.clear()
                    completed[request.key] = result.observedTypes
                    restartDaemon(request.file)
                }
            }
        }, DEBOUNCE_MILLIS, TimeUnit.MILLISECONDS)
    }

    private fun cancelStaleSnapshots(current: SnapshotKey) {
        inFlight.asSequence()
            .filter { it.fileUrl == current.fileUrl && it != current }
            .toList()
            .forEach { stale ->
                inFlight.remove(stale)
                scheduled.remove(stale)?.cancel(false)
                active.remove(stale)?.cancel()
            }
    }

    private fun restartDaemon(file: VirtualFile) {
        ApplicationManager.getApplication().invokeLater {
            if (!project.isDisposed) DaemonCodeAnalyzer.getInstance(project).restart(file)
        }
    }

    override fun dispose() {
        scheduled.values.forEach { it.cancel(false) }
        active.values.forEach { it.cancel() }
        synchronized(workerLock) {
            worker?.close()
            worker = null
            workerRuntime = null
        }
        scheduled.clear()
        active.clear()
        inFlight.clear()
        completed.clear()
        debounceExecutor.shutdownNow()
    }

    private data class ConfiguredRuntime(val target: RuntimeTarget, val executable: String) {
        val key: String get() = "$target\u0000$executable"
    }
    private data class SnapshotKey(val fileUrl: String, val sourceDigest: String, val runtimeKey: String)
    private data class SnapshotRequest(
        val key: SnapshotKey,
        val source: String,
        val requestedNames: Set<String>,
        val runtime: ConfiguredRuntime,
        val fileName: String,
        val file: VirtualFile,
    )

    private fun workerFor(runtime: ConfiguredRuntime): SageLiveTypeWorker = synchronized(workerLock) {
        if (workerRuntime != runtime) {
            worker?.close()
            worker = SageLiveTypeWorker(runtime.target, runtime.executable, MAX_OUTPUT_BYTES)
            workerRuntime = runtime
        }
        checkNotNull(worker)
    }

    companion object {
        private const val LIVE_RESULT_NAME = "__sage_ide_live_result"
        private const val MAX_SOURCE_BYTES = 256 * 1024
        private const val MAX_OUTPUT_BYTES = 128 * 1024
        private const val MAX_CACHED_SNAPSHOTS = 64
        private const val DEBOUNCE_MILLIS = 650L
        // A fresh WSL Sage process can spend more than ten seconds loading
        // finite-field and elliptic-curve backends.  This is a background
        // deadline, not an editor wait; a shorter cap would discard correct
        // snapshots before they can update completion.
        private val LIVE_TYPE_PROBE_DEADLINE: Duration = Duration.ofSeconds(30)
        private val IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")

        fun getInstance(project: Project): SageLiveTypeSnapshotService = project.getService(SageLiveTypeSnapshotService::class.java)

        private fun isSafeIdentifier(name: String): Boolean = name.matches(IDENTIFIER)
        private fun sha256(source: String): String = MessageDigest.getInstance("SHA-256")
            .digest(source.toByteArray(StandardCharsets.UTF_8))
            .joinToString("") { byte -> "%02x".format(byte) }

    }
}

/**
 * Maps only an exact observed class or its immediate concrete implementation
 * parent.  A missing stub must stay unknown: walking farther down the MRO
 * would silently turn an exact runtime result into a public base-class type.
 */
internal object SageObservedTypeResolver {
    fun resolve(project: Project, observed: SageObservedType): PyType? {
        val candidates = listOf(observed.runtimeClass) + observed.methodResolutionOrder.drop(1).take(1)
        return candidates.asSequence()
            .mapNotNull { SageStubIndex.findClassByCanonicalName(project, it) }
            .firstOrNull()
            ?.takeIf { it.isValid }
            ?.let { PyClassTypeImpl(it, false) }
    }
}
