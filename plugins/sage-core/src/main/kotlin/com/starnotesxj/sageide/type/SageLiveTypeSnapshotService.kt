package com.starnotesxj.sageide.type

import com.intellij.codeInsight.daemon.DaemonCodeAnalyzer
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileEditor.FileDocumentManager
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
    private val evidence = SageLiveTypeEvidenceCache<SnapshotKey, Map<String, SageObservedType>>(
        MAX_CACHED_SNAPSHOTS,
        FAILURE_RETRY_MILLIS,
    )
    private val runEvidence = SageLiveTypeEvidenceCache<RunEvidenceKey, RunEvidence>(
        MAX_CACHED_SNAPSHOTS,
        FAILURE_RETRY_MILLIS,
    )
    private val inFlight = ConcurrentHashMap.newKeySet<SnapshotKey>()
    private val scheduled = ConcurrentHashMap<SnapshotKey, ScheduledFuture<*>>()
    private val active = ConcurrentHashMap<SnapshotKey, SageRuntimeProbeHandle<*>>()
    private val workerLock = Any()
    private var workerRuntime: ConfiguredRuntime? = null
    private var worker: SageLiveTypeWorker? = null
    private var workerIdleClose: ScheduledFuture<*>? = null
    private val debounceExecutor: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "sage-live-type-snapshot").apply { isDaemon = true }
    }

    fun typeForReference(reference: PyReferenceExpression): PyType? {
        if (reference.qualifier != null || PsiTreeUtil.getParentOfType(reference, PyFunction::class.java) != null) return null
        val name = reference.referencedName ?: return null
        observedRunType(reference, name)?.let { return it }
        return typeFor(reference, name, includeContainingStatement = false, scheduleIfAbsent = false)
    }

    /**
     * Starts an isolated query only for a receiver on which the user is asking
     * for members (for example the `P` in `P.log`). Ordinary references are
     * requested repeatedly during daemon passes, and probing each would turn a
     * static edit into a Sage workload.
     */
    fun scheduleTypeForMemberReceiver(reference: PyReferenceExpression): PyType? {
        if (!acceptsMemberProbe(reference)) return null
        val name = reference.referencedName ?: return null
        observedRunType(reference, name)?.let { return it }
        return typeFor(reference, name, includeContainingStatement = false, scheduleIfAbsent = true)
    }

    fun typeForTarget(target: PyTargetExpression): PyType? {
        if (target.qualifier != null || PsiTreeUtil.getParentOfType(target, PyFunction::class.java) != null) return null
        val name = target.name ?: return null
        observedRunType(target, name)?.let { return it }
        // Assignment targets are queried on every daemon pass. Static contracts
        // remain the first answer; a later member completion can request a
        // bounded live fallback if one is genuinely needed.
        return typeFor(target, name, includeContainingStatement = true, scheduleIfAbsent = false)
    }

    /**
     * Receives one normal Sage file run after the original Sage runner exits.
     * The sidecar is accepted only for the exact saved document bytes and
     * runtime key that launched it.  The saved document text is retained only
     * to permit a whitespace-only append before a newly typed completion
     * reference; it remains session evidence, never an API index update or a
     * reusable static return contract.
     */
    internal fun recordRunEvidence(
        file: VirtualFile,
        sourceDigest: String,
        sourceText: String? = null,
        runtimeKey: String,
        observedTypes: Map<String, SageObservedType>,
    ) {
        if (observedTypes.isEmpty() || project.isDisposed || !file.isValid) return
        runEvidence.recordSuccess(
            RunEvidenceKey(file.url, sourceDigest, runtimeKey),
            RunEvidence(
                observedTypes,
                sourceText?.takeIf { it.toByteArray(StandardCharsets.UTF_8).size <= MAX_SOURCE_BYTES },
            ),
        )
        restartDaemon(file)
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
        if (!acceptsDynamicCallProbe(call)) return null
        val request = callSnapshotRequest(call) ?: return null
        val name = LIVE_RESULT_NAME
        val observed = evidence.completed(request.key)?.get(name)
        if (observed != null) return SageObservedTypeResolver.resolve(project, observed)
        schedule(request)
        return null
    }

    private fun typeFor(
        anchor: com.intellij.psi.PsiElement,
        name: String,
        includeContainingStatement: Boolean,
        scheduleIfAbsent: Boolean,
    ): PyType? {
        if (!isSafeIdentifier(name) || !SageRunSettings.getInstance().getState().liveTypeProbingEnabled) return null
        val request = snapshotRequest(anchor, name, includeContainingStatement) ?: return null
        val observed = evidence.completed(request.key)?.get(name)
        if (observed != null) return SageObservedTypeResolver.resolve(project, observed)
        if (scheduleIfAbsent) schedule(request)
        return null
    }

    internal fun acceptsMemberProbe(reference: PyReferenceExpression): Boolean {
        if (PsiTreeUtil.getParentOfType(reference, PyFunction::class.java) != null) return false
        val memberReference = reference.parent as? PyReferenceExpression ?: return false
        return memberReference.qualifier === reference
    }

    /**
     * A global call can be a user function with arbitrary effects. Its assigned
     * result is still available to a later `value.member` request, so reserve
     * eager call snapshots for the member-call result the user is inspecting.
     */
    internal fun acceptsDynamicCallProbe(call: PyCallExpression): Boolean {
        if (PsiTreeUtil.getParentOfType(call, PyFunction::class.java) != null) return false
        return (call.callee as? PyReferenceExpression)?.qualifier != null
    }

    private fun observedRunType(anchor: com.intellij.psi.PsiElement, name: String): PyType? {
        if (!SageRunSettings.getInstance().getState().liveTypeProbingEnabled || !isSafeIdentifier(name)) return null
        val file = anchor.containingFile as? PyFile ?: return null
        if (!SageFileUtils.isSageFile(file) || SageStubIndex.isSageStubFile(file)) return null
        val virtualFile = file.virtualFile ?: return null
        val document = FileDocumentManager.getInstance().getDocument(virtualFile)
        val runtime = configuredRuntime() ?: return null
        val evidence = if (document != null && FileDocumentManager.getInstance().isDocumentUnsaved(document)) {
            runEvidence.completedEntries()
                .asSequence()
                .filter { (key, value) ->
                    key.fileUrl == virtualFile.url &&
                        key.runtimeKey == runtime.key &&
                        name in value.observedTypes &&
                        isWhitespaceOnlyAppendBefore(anchor, document.text, value.sourceText)
                }
                // Several historic runs may be cached for one file.  The
                // longest matching executed prefix is the only current one.
                .maxByOrNull { (_, value) -> value.sourceText?.length ?: -1 }
                ?.second
        } else {
            val digest = runCatching { sha256(virtualFile.contentsToByteArray()) }.getOrNull() ?: return null
            runEvidence.completed(RunEvidenceKey(virtualFile.url, digest, runtime.key))
        } ?: return null
        val observed = evidence.observedTypes[name] ?: return null
        return SageObservedTypeResolver.resolve(project, observed)
    }

    /**
     * Typing ``P.`` after a completed run makes the document unsaved.  It is
     * still safe to use the run's type for that new reference when the executed
     * prefix is byte-for-byte represented by the saved document text and the
     * user added only whitespace before the reference.  Any edit to the
     * executed source, or any new statement before the reference, stays
     * fail-closed so an old value of ``P`` cannot leak past a reassignment.
     */
    private fun isWhitespaceOnlyAppendBefore(anchor: com.intellij.psi.PsiElement, currentText: String, savedSource: String?): Boolean {
        if (savedSource == null) return false
        if (currentText == savedSource) return true
        if (!currentText.startsWith(savedSource)) return false
        val anchorOffset = anchor.textRange.startOffset
        if (anchorOffset < savedSource.length || anchorOffset > currentText.length) return false
        return currentText.substring(savedSource.length, anchorOffset).all(Char::isWhitespace)
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
        if (!evidence.maySchedule(request.key)) return
        cancelStaleSnapshots(request.key)
        if (!inFlight.add(request.key)) return
        cancelWorkerIdleClose()
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
                    evidence.recordSuccess(request.key, result.observedTypes)
                    restartDaemon(request.file)
                } else if (result?.status != RuntimeExecutionStatus.CANCELLED) {
                    // A deterministic source error or an unavailable runtime must
                    // not cause an endless daemon -> worker -> daemon loop.  The
                    // backoff is keyed by this exact source and runtime only.
                    evidence.recordFailure(request.key)
                }
                scheduleWorkerCloseWhenIdle()
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

    /**
     * Sage imports a large algebra stack. Keep it warm briefly for an active
     * completion session, then release the WSL process instead of retaining
     * that memory until the project is closed.
     */
    private fun scheduleWorkerCloseWhenIdle() {
        if (inFlight.isNotEmpty() || active.isNotEmpty()) return
        synchronized(workerLock) {
            workerIdleClose?.cancel(false)
            val runtime = workerRuntime ?: return
            workerIdleClose = debounceExecutor.schedule({
                synchronized(workerLock) {
                    workerIdleClose = null
                    if (inFlight.isEmpty() && active.isEmpty() && workerRuntime == runtime) {
                        worker?.close()
                        worker = null
                        workerRuntime = null
                    }
                }
            }, WORKER_IDLE_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
        }
    }

    private fun cancelWorkerIdleClose() = synchronized(workerLock) {
        workerIdleClose?.cancel(false)
        workerIdleClose = null
    }

    override fun dispose() {
        scheduled.values.forEach { it.cancel(false) }
        active.values.forEach { it.cancel() }
        synchronized(workerLock) {
            workerIdleClose?.cancel(false)
            workerIdleClose = null
            worker?.close()
            worker = null
            workerRuntime = null
        }
        scheduled.clear()
        active.clear()
        inFlight.clear()
        evidence.clear()
        runEvidence.clear()
        debounceExecutor.shutdownNow()
    }

    private data class ConfiguredRuntime(val target: RuntimeTarget, val executable: String) {
        val key: String get() = "$target\u0000$executable"
    }
    private data class SnapshotKey(val fileUrl: String, val sourceDigest: String, val runtimeKey: String)
    private data class RunEvidenceKey(val fileUrl: String, val sourceDigest: String, val runtimeKey: String)
    private data class RunEvidence(val observedTypes: Map<String, SageObservedType>, val sourceText: String?)
    private data class SnapshotRequest(
        val key: SnapshotKey,
        val source: String,
        val requestedNames: Set<String>,
        val runtime: ConfiguredRuntime,
        val fileName: String,
        val file: VirtualFile,
    )

    private fun workerFor(runtime: ConfiguredRuntime): SageLiveTypeWorker = synchronized(workerLock) {
        workerIdleClose?.cancel(false)
        workerIdleClose = null
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
        private const val FAILURE_RETRY_MILLIS = 10_000L
        private const val DEBOUNCE_MILLIS = 650L
        private const val WORKER_IDLE_TIMEOUT_MILLIS = 10_000L
        // A fresh WSL Sage process can spend more than ten seconds loading
        // finite-field and elliptic-curve backends.  This is a background
        // deadline, not an editor wait; a shorter cap would discard correct
        // snapshots before they can update completion.
        private val LIVE_TYPE_PROBE_DEADLINE: Duration = Duration.ofSeconds(30)
        private val IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")

        fun getInstance(project: Project): SageLiveTypeSnapshotService = project.getService(SageLiveTypeSnapshotService::class.java)

        private fun isSafeIdentifier(name: String): Boolean = name.matches(IDENTIFIER)
        internal fun runtimeKey(target: RuntimeTarget, executable: String): String = "$target\u0000$executable"

        private fun sha256(source: String): String = sha256(source.toByteArray(StandardCharsets.UTF_8))
        private fun sha256(bytes: ByteArray): String = MessageDigest.getInstance("SHA-256")
            .digest(bytes)
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
