package com.starnotesxj.sageide.highlight

import com.intellij.codeInspection.LocalQuickFix
import com.intellij.codeInspection.InspectionManager
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.PsiFile

/** A quick-fix whose textual replacement is safe to preview and apply in a batch. */
internal interface SageBatchTextReplacement : LocalQuickFix {
    val expectedText: String
    val replacementText: String
}

internal data class SageTextReplacement(
    val startOffset: Int,
    val endOffset: Int,
    val expectedText: String,
    val replacementText: String,
)

internal data class SageBatchFixPreview(
    val beforeText: String,
    val afterText: String,
    val replacements: List<SageTextReplacement>,
)

internal data class SageBatchFixInput(
    val path: String,
    val source: String,
    val edits: List<SageTextReplacement>,
)

internal data class SageBatchFileFixPreview(
    val path: String,
    val beforeText: String,
    val afterText: String,
    val replacements: List<SageTextReplacement>,
)

internal data class SageProjectBatchFixPreview(
    val files: List<SageBatchFileFixPreview>,
) {
    val replacementCount: Int
        get() = files.sumOf { it.replacements.size }
}

internal object SageBatchFixPlanner {
    /** Returns null when edits are empty, stale, out of range, or overlapping. */
    fun plan(source: String, edits: List<SageTextReplacement>): SageBatchFixPreview? {
        if (edits.isEmpty()) return null
        val ordered = edits.sortedBy(SageTextReplacement::startOffset)
        var previousEnd = -1
        for (edit in ordered) {
            if (edit.startOffset < previousEnd || edit.startOffset < 0 || edit.endOffset > source.length) return null
            if (edit.endOffset <= edit.startOffset || edit.endOffset - edit.startOffset != edit.expectedText.length) return null
            if (source.substring(edit.startOffset, edit.endOffset) != edit.expectedText) return null
            previousEnd = edit.endOffset
        }

        val after = StringBuilder(source)
        ordered.asReversed().forEach { edit ->
            after.replace(edit.startOffset, edit.endOffset, edit.replacementText)
        }
        return SageBatchFixPreview(source, after.toString(), ordered)
    }

    /** Returns null if any selected fix is stale/unsafe or no file has an applicable fix. */
    fun planFiles(inputs: List<SageBatchFixInput>): SageProjectBatchFixPreview? {
        if (inputs.isEmpty() || inputs.map(SageBatchFixInput::path).distinct().size != inputs.size) return null

        val previews = mutableListOf<SageBatchFileFixPreview>()
        for (input in inputs.sortedBy(SageBatchFixInput::path)) {
            if (input.edits.isEmpty()) continue
            val preview = plan(input.source, input.edits) ?: return null
            previews += SageBatchFileFixPreview(
                path = input.path,
                beforeText = preview.beforeText,
                afterText = preview.afterText,
                replacements = preview.replacements,
            )
        }
        return previews.takeIf { it.isNotEmpty() }?.let(::SageProjectBatchFixPreview)
    }
}

/** Builds the exact preview consumed by both editor and Project View actions. */
internal object SageBatchFixPreviewFactory {
    fun forFile(project: Project, file: PsiFile): SageBatchFixPreview? {
        if (!isSageFile(project, file)) return null
        val document = PsiDocumentManager.getInstance(project).getDocument(file) ?: return null
        return SageBatchFixPlanner.plan(file.text, collectEdits(project, file))
            ?.takeIf { document.text == it.beforeText }
    }

    fun forFiles(project: Project, files: List<PsiFile>): SageProjectBatchFixPreview? {
        if (files.isEmpty() || files.any { !isSageFile(project, it) }) return null
        val inputs = files.map { file ->
            val document = PsiDocumentManager.getInstance(project).getDocument(file) ?: return null
            SageBatchFixInput(file.virtualFile.path, file.text, collectEdits(project, file))
                .takeIf { document.text == it.source } ?: return null
        }
        return SageBatchFixPlanner.planFiles(inputs)
    }

    private fun isSageFile(project: Project, file: PsiFile): Boolean =
        !project.isDisposed && file.isValid && file.name.endsWith(".sage", ignoreCase = true)

    private fun collectEdits(project: Project, file: PsiFile): List<SageTextReplacement> =
        SageXorInspection().processFile(file, InspectionManager.getInstance(project)).mapNotNull { problem ->
            val element = problem.psiElement.takeIf { it.isValid } ?: return@mapNotNull null
            val fix = problem.fixes.orEmpty().filterIsInstance<SageBatchTextReplacement>().firstOrNull()
                ?: return@mapNotNull null
            val range = element.textRange
            SageTextReplacement(range.startOffset, range.endOffset, fix.expectedText, fix.replacementText)
        }
}
