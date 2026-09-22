package com.starnotesxj.sageide.inline

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.StartupActivity
import com.intellij.util.concurrency.AppExecutorUtil
import java.util.concurrent.TimeUnit

/** Starts the optional local scorer after project opening, never on a keypress. */
class SageInlineWarmupStartupActivity : StartupActivity.DumbAware {
    override fun runActivity(project: Project) {
        if (ApplicationManager.getApplication().isUnitTestMode) return
        AppExecutorUtil.getAppScheduledExecutorService().schedule({
            if (!project.isDisposed) {
                SageInlineNativeRuntime.getInstance(project).warmUp()
            }
        }, WARMUP_DELAY_SECONDS, TimeUnit.SECONDS)
    }

    private companion object {
        private const val WARMUP_DELAY_SECONDS = 5L
    }
}
