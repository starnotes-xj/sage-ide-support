package com.starnotesxj.sageide.inline

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.PathManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.starnotesxj.sageide.run.SageRunSettings
import java.nio.file.Path

/**
 * Owns the optional native scorer for one project.
 *
 * Absence of a bundled platform binary is normal during source-only and
 * cross-platform builds. In that case the normal in-process semantic scorer
 * remains the whole implementation and no process is launched.
 */
@Service(Service.Level.PROJECT)
class SageInlineNativeRuntime(private val project: Project) : Disposable {
    @Volatile
    private var backend: SageInlineScoringBackend = SageInlineSemanticScoringBackend
    @Volatile
    private var scorer: SageNativeInlineProcessScorer? = null

    @Synchronized
    fun warmUp() {
        if (project.isDisposed || scorer != null || !SageRunSettings.getInstance().state.nativeInlineScoringEnabled) return
        val cache = Path.of(PathManager.getSystemPath(), "sage-math-core", "inline-native")
        val executable = SageNativeInlineExecutable.extractTo(cache) ?: return
        val candidate = SageNativeInlineProcessScorer(executable)
        if (candidate.warmUp()) {
            scorer = candidate
            backend = SageNativeInlineScoringBackend(candidate)
        } else {
            candidate.close()
        }
    }

    internal suspend fun score(request: SageInlineScoringRequest): SageInlinePrediction? = backend.predict(request)

    /** Applies a settings change immediately; disabling releases the child process. */
    @Synchronized
    fun refreshEnabledState() {
        if (!SageRunSettings.getInstance().state.nativeInlineScoringEnabled) {
            deactivateLocked()
        }
    }

    @Synchronized
    override fun dispose() {
        deactivateLocked()
    }

    private fun deactivateLocked() {
        backend = SageInlineSemanticScoringBackend
        scorer?.close()
        scorer = null
    }

    companion object {
        fun getInstance(project: Project): SageInlineNativeRuntime = project.service()
    }
}
