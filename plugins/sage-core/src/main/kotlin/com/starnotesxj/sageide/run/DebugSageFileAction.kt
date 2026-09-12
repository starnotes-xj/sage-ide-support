package com.starnotesxj.sageide.run

import com.intellij.execution.ProgramRunnerUtil
import com.intellij.execution.RunManager
import com.intellij.execution.executors.DefaultDebugExecutor
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.project.DumbAwareAction
import com.starnotesxj.sageide.SageBundle

/** Launches the current Sage file through PyCharm's Python debug executor. */
class DebugSageFileAction : DumbAwareAction(SageBundle.message("run.action.debug")) {

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val file = selectedSageFile(e) ?: return
        if (file.extension != "sage") return

        val type = SageRunConfigurationType.getInstance()
        val runManager = RunManager.getInstance(project)
        val factory = type.configurationFactories.single()
        val existing = runManager.allSettings
            .filter {
                val configuration = it.configuration as? SageRunConfiguration
                configuration?.scriptPath == file.path
            }
            .firstOrNull()
        val settings = existing ?: runManager.createConfiguration(file.nameWithoutExtension, factory).also {
            (it.configuration as SageRunConfiguration).scriptPath = file.path
            runManager.addConfiguration(it)
        }
        runManager.selectedConfiguration = settings
        ProgramRunnerUtil.executeConfiguration(
            settings,
            DefaultDebugExecutor.getDebugExecutorInstance(),
        )
    }

    override fun update(e: AnActionEvent) {
        e.presentation.text = SageBundle.message("run.action.debug")
        e.presentation.description = SageBundle.message("run.action.debug.description")
        val file = selectedSageFile(e)
        val available = file?.extension == "sage"
        e.presentation.isEnabledAndVisible = available
    }

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT
}
