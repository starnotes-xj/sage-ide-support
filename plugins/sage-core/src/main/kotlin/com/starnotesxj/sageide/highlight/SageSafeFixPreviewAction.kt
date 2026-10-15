package com.starnotesxj.sageide.highlight

import com.intellij.diff.DiffContentFactory
import com.intellij.diff.DiffDialogHints
import com.intellij.diff.DiffManager
import com.intellij.diff.requests.SimpleDiffRequest
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.command.WriteCommandAction
import com.intellij.openapi.progress.ProgressIndicator
import com.intellij.openapi.progress.Task
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile
import java.util.concurrent.Callable

/** Previews all currently applicable Sage XOR fixes in the active .sage file. */
class SageSafeFixPreviewAction : AnAction("Review and Apply Sage Safe Fixes") {

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT

    override fun update(event: AnActionEvent) {
        val file = event.getData(CommonDataKeys.PSI_FILE)
        event.presentation.isEnabledAndVisible = event.project != null && file?.name?.endsWith(".sage") == true
    }

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        val file = event.getData(CommonDataKeys.PSI_FILE)?.takeIf { it.name.endsWith(".sage") } ?: return

        object : Task.Backgroundable(project, ACTION_TITLE, true) {
            override fun run(indicator: ProgressIndicator) {
                val preview = ReadAction.nonBlocking(Callable { createPreview(project, file) })
                    .wrapProgress(indicator)
                    .executeSynchronously()
                ApplicationManager.getApplication().invokeLater(
                    { showPreviewAndConfirm(project, file, preview) },
                    ModalityState.nonModal(),
                )
            }
        }.queue()
    }

    private fun createPreview(project: Project, file: PsiFile): SageBatchFixPreview? {
        return SageBatchFixPreviewFactory.forFile(project, file)
    }

    private fun showPreviewAndConfirm(project: Project, file: PsiFile, preview: SageBatchFixPreview?) {
        if (project.isDisposed || !file.isValid) return
        if (preview == null) {
            Messages.showInfoMessage(project, "No safe Sage fixes were found in the current file.", ACTION_TITLE)
            return
        }

        val request = SimpleDiffRequest(
            ACTION_TITLE,
            DiffContentFactory.getInstance().create(project, preview.beforeText, file.fileType),
            DiffContentFactory.getInstance().create(project, preview.afterText, file.fileType),
            "Current file",
            "After ${preview.replacements.size} Sage fix(es)",
        )
        DiffManager.getInstance().showDiff(project, request, DiffDialogHints.MODAL)
        if (project.isDisposed || !file.isValid) return

        val accepted = Messages.showYesNoDialog(
            project,
            "Apply ${preview.replacements.size} reviewed Sage fix(es) to ${file.name}?",
            ACTION_TITLE,
            Messages.getQuestionIcon(),
        ) == Messages.YES
        if (!accepted) return

        var applied = false
        var stale = false
        WriteCommandAction.writeCommandAction(project, file)
            .withName(ACTION_TITLE)
            .run<RuntimeException> {
                val document = PsiDocumentManager.getInstance(project).getDocument(file)
                if (document == null || document.text != preview.beforeText) {
                    stale = true
                    return@run
                }
                preview.replacements.sortedByDescending(SageTextReplacement::startOffset).forEach { edit ->
                    document.replaceString(edit.startOffset, edit.endOffset, edit.replacementText)
                }
                PsiDocumentManager.getInstance(project).commitDocument(document)
                applied = true
            }

        if (stale) {
            Messages.showWarningDialog(
                project,
                "The file changed after the preview was created. No fixes were applied; run the preview again.",
                ACTION_TITLE,
            )
        } else if (applied) {
            Messages.showInfoMessage(project, "Applied ${preview.replacements.size} Sage fix(es).", ACTION_TITLE)
        }
    }

    private companion object {
        const val ACTION_TITLE = "Review Sage Safe Fixes"
    }
}
