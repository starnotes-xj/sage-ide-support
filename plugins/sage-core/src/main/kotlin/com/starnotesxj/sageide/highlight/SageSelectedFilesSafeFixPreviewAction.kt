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
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiManager
import java.util.concurrent.Callable

/** Reviews safe textual Sage fixes across the .sage files selected in Project View. */
class SageSelectedFilesSafeFixPreviewAction : AnAction(ACTION_TITLE) {

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.BGT

    override fun update(event: AnActionEvent) {
        event.presentation.isEnabledAndVisible = event.project != null && selectedSageFiles(event).isNotEmpty()
    }

    override fun actionPerformed(event: AnActionEvent) {
        val project = event.project ?: return
        val selectedFiles = selectedSageFiles(event)
        if (selectedFiles.isEmpty()) return

        object : Task.Backgroundable(project, ACTION_TITLE, true) {
            override fun run(indicator: ProgressIndicator) {
                val prepared = ReadAction.nonBlocking(Callable { createPreview(project, selectedFiles, indicator) })
                    .wrapProgress(indicator)
                    .executeSynchronously()
                ApplicationManager.getApplication().invokeLater(
                    { showPreviewAndConfirm(project, prepared) },
                    ModalityState.nonModal(),
                )
            }
        }.queue()
    }

    private fun createPreview(
        project: Project,
        selectedFiles: List<VirtualFile>,
        indicator: ProgressIndicator,
    ): PreparedPreview? {
        if (project.isDisposed) return null
        val psiFilesByPath = linkedMapOf<String, PsiFile>()
        for (virtualFile in selectedFiles) {
            indicator.checkCanceled()
            if (!virtualFile.isValid) return null
            val psiFile = PsiManager.getInstance(project).findFile(virtualFile) ?: return null
            psiFilesByPath[virtualFile.path] = psiFile
        }
        val preview = SageBatchFixPreviewFactory.forFiles(project, psiFilesByPath.values.toList()) ?: return null
        if (preview.files.any { it.path !in psiFilesByPath }) return null
        return PreparedPreview(preview, psiFilesByPath)
    }

    private fun showPreviewAndConfirm(project: Project, prepared: PreparedPreview?) {
        if (project.isDisposed) return
        if (prepared == null) {
            Messages.showInfoMessage(project, "No safe Sage fixes were found in the selected files.", ACTION_TITLE)
            return
        }

        val firstPsiFile = prepared.preview.files.firstNotNullOfOrNull { prepared.psiFilesByPath[it.path] }
            ?: return
        val factory = DiffContentFactory.getInstance()
        val request = SimpleDiffRequest(
            ACTION_TITLE,
            factory.create(project, render(prepared.preview, after = false), firstPsiFile.fileType),
            factory.create(project, render(prepared.preview, after = true), firstPsiFile.fileType),
            "Selected Sage files",
            "After ${prepared.preview.replacementCount} fix(es) in ${prepared.preview.files.size} file(s)",
        )
        DiffManager.getInstance().showDiff(project, request, DiffDialogHints.MODAL)
        if (project.isDisposed) return

        val accepted = Messages.showYesNoDialog(
            project,
            "Apply ${prepared.preview.replacementCount} reviewed Sage fix(es) across ${prepared.preview.files.size} selected file(s)?",
            ACTION_TITLE,
            Messages.getQuestionIcon(),
        ) == Messages.YES
        if (!accepted) return

        val targetPsiFiles = prepared.preview.files.mapNotNull { prepared.psiFilesByPath[it.path] }
        if (targetPsiFiles.size != prepared.preview.files.size) {
            showStaleWarning(project)
            return
        }

        var applied = false
        var stale = false
        WriteCommandAction.writeCommandAction(project, *targetPsiFiles.toTypedArray())
            .withName(ACTION_TITLE)
            .run<RuntimeException> {
                val documents = prepared.preview.files.map { filePreview ->
                    val psiFile = prepared.psiFilesByPath[filePreview.path]?.takeIf { it.isValid }
                    val document = psiFile?.let { PsiDocumentManager.getInstance(project).getDocument(it) }
                    if (document == null || document.text != filePreview.beforeText) {
                        stale = true
                        return@run
                    }
                    filePreview to document
                }
                if (stale) return@run

                documents.forEach { (filePreview, document) ->
                    filePreview.replacements.sortedByDescending(SageTextReplacement::startOffset).forEach { edit ->
                        document.replaceString(edit.startOffset, edit.endOffset, edit.replacementText)
                    }
                    PsiDocumentManager.getInstance(project).commitDocument(document)
                }
                applied = true
            }

        when {
            stale -> showStaleWarning(project)
            applied -> Messages.showInfoMessage(
                project,
                "Applied ${prepared.preview.replacementCount} Sage fix(es) across ${prepared.preview.files.size} file(s).",
                ACTION_TITLE,
            )
        }
    }

    private fun render(preview: SageProjectBatchFixPreview, after: Boolean): String = buildString {
        preview.files.forEachIndexed { index, file ->
            if (index > 0) append("\n\n")
            append("===== ").append(file.path).append(" =====\n")
            append(if (after) file.afterText else file.beforeText)
            if (!endsWith('\n')) append('\n')
        }
    }

    private fun showStaleWarning(project: Project) {
        Messages.showWarningDialog(
            project,
            "A selected file changed after the preview was created. No fixes were applied; run the preview again.",
            ACTION_TITLE,
        )
    }

    private fun selectedSageFiles(event: AnActionEvent): List<VirtualFile> =
        event.getData(CommonDataKeys.VIRTUAL_FILE_ARRAY)
            .orEmpty()
            .filter { it.isValid && !it.isDirectory && it.extension.equals("sage", ignoreCase = true) }
            .distinctBy(VirtualFile::getPath)

    private data class PreparedPreview(
        val preview: SageProjectBatchFixPreview,
        val psiFilesByPath: Map<String, PsiFile>,
    )

    private companion object {
        const val ACTION_TITLE = "Review and Apply Sage Safe Fixes in Selected Files"
    }
}
