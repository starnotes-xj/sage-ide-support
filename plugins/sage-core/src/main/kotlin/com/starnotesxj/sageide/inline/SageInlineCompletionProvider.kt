package com.starnotesxj.sageide.inline

import com.intellij.codeInsight.inline.completion.DebouncedInlineCompletionProvider
import com.intellij.codeInsight.inline.completion.InlineCompletionEvent
import com.intellij.codeInsight.inline.completion.InlineCompletionProviderID
import com.intellij.codeInsight.inline.completion.InlineCompletionRequest
import com.intellij.codeInsight.inline.completion.suggestion.InlineCompletionSingleSuggestion
import com.intellij.codeInsight.inline.completion.suggestion.InlineCompletionSuggestion
import com.intellij.codeInsight.inline.completion.elements.InlineCompletionGrayTextElement
import com.intellij.openapi.application.readAction
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.util.UserDataHolderBase
import com.starnotesxj.sageide.sugar.SageFileType
import kotlinx.coroutines.flow.flowOf
import kotlin.time.Duration
import kotlin.time.Duration.Companion.milliseconds

/**
 * Sage's own async inline-completion entry point.
 *
 * [DebouncedInlineCompletionProvider] provides the two critical performance
 * invariants used by JetBrains' own provider: a newer edit cancels the older
 * coroutine, and automatic typing waits for a quiet interval before the
 * semantic backend is touched. No process, index rebuild, Sage execution, or
 * WSL request is started from the typing event itself.
 */
class SageInlineCompletionProvider : DebouncedInlineCompletionProvider() {
    override val id: InlineCompletionProviderID = InlineCompletionProviderID("SageSemanticInlineCompletion")

    override fun isEnabled(event: InlineCompletionEvent): Boolean {
        val editor = event.editorOrNull() ?: return false
        if (FileDocumentManager.getInstance().getFile(editor.document)?.fileType !== SageFileType.INSTANCE) return false
        return when (event) {
            is InlineCompletionEvent.DirectCall -> true
            is InlineCompletionEvent.DocumentChange -> event.typing.typed.length == 1 &&
                event.typing.typed.single().isLetterOrDigit()
            else -> false
        }
    }

    override suspend fun getDebounceDelay(request: InlineCompletionRequest): Duration = DEBOUNCE_DELAY

    override suspend fun getSuggestionDebounced(request: InlineCompletionRequest): InlineCompletionSuggestion {
        val service = SageInlinePredictionService.getInstance(request.file.project)
        val scoringRequest = readAction {
            service.prepareScoringRequest(request.file, request.endOffset)
        } ?: return InlineCompletionSuggestion.Empty
        val prediction = SageInlineNativeRuntime.getInstance(request.file.project).score(scoringRequest)
            ?: return InlineCompletionSuggestion.Empty
        return InlineCompletionSingleSuggestion.build(
            UserDataHolderBase(),
            flowOf(InlineCompletionGrayTextElement(prediction.suffix)),
        )
    }

    private fun InlineCompletionEvent.editorOrNull(): Editor? = when (this) {
        is InlineCompletionEvent.DocumentChange -> editor
        is InlineCompletionEvent.DirectCall -> editor
        is InlineCompletionEvent.Backspace -> editor
        else -> null
    }

    private companion object {
        val DEBOUNCE_DELAY: Duration = 220.milliseconds
    }
}
