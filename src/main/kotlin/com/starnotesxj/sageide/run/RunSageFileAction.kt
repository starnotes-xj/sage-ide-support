package com.starnotesxj.sageide.run

import com.intellij.execution.ProgramRunnerUtil
import com.intellij.execution.RunManager
import com.intellij.execution.executors.DefaultRunExecutor
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.project.DumbAwareAction

/**
 * Runs the current Sage file through the Sage run configuration; used as the
 * gutter (line marker) action and the editor context-menu action.
 */
class RunSageFileAction : DumbAwareAction("Run Sage Script") {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE) ?: return
        if (file.extension != "sage") return

        val type = SageRunConfigurationType.getInstance()
        val runManager = RunManager.getInstance(project)
        val factory = type.configurationFactories.single()
        val existing = runManager.allSettings
            .filter { it.configuration is SageRunConfiguration && (it.configuration as SageRunConfiguration).scriptPath == file.path }
            .firstOrNull()
        val settings = existing ?: runManager.createConfiguration(file.nameWithoutExtension, factory).also {
            (it.configuration as SageRunConfiguration).scriptPath = file.path
            runManager.addConfiguration(it)
        }
        runManager.selectedConfiguration = settings
        ProgramRunnerUtil.executeConfiguration(settings, DefaultRunExecutor.getRunExecutorInstance())
    }

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT
}
