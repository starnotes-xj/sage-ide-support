package com.starnotesxj.sageide.run

import com.intellij.openapi.project.Project
import com.intellij.openapi.startup.StartupActivity

/** Starts local/WSL Sage discovery after the IDE has finished opening a project. */
class SageRuntimeDiscoveryStartupActivity : StartupActivity.DumbAware {
    override fun runActivity(project: Project) {
        if (!project.isDisposed) {
            SageRuntimeService.getInstance().discoverInstalledRuntimesAsync()
        }
    }
}
