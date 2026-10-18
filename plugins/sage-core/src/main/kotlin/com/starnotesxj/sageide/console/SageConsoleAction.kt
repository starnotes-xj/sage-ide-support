package com.starnotesxj.sageide.console

import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys

/**
 * Tools → Sage Console: opens the interactive Sage REPL bound to the
 * configured runtime.  Available wherever a project is open; startup errors
 * (no runtime configured, unsupported mode) surface as an error dialog from
 * the runner.
 */
class SageConsoleAction : AnAction(
    "Sage Console",
    "Open an interactive Sage REPL for the configured SageMath runtime",
    null,
) {
    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        SageConsoleRunner.open(project)
    }

    override fun update(event: AnActionEvent) {
        event.presentation.isEnabledAndVisible = event.project != null
    }

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT
}
