package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.inline.completion.InlineCompletionProvider
import com.intellij.lang.Language
import com.intellij.ml.inline.completion.impl.lang.MLCompletionEditorLanguageResolver
import com.intellij.openapi.editor.Editor
import com.intellij.openapi.fileTypes.FileType
import com.intellij.openapi.fileEditor.FileDocumentManager

/**
 * Keeps Full Line's Python model out of Sage source editors.
 *
 * [SageLanguage] is a Python dialect, but Python PSI leaves intentionally keep
 * [com.jetbrains.python.PythonLanguage] as their language.  Full Line selects
 * its language from the leaf at the caret, and would therefore initialise the
 * Python ML request pipeline while editing a `.sage` file.  Its public
 * language-resolver extension point lets a dialect supply the editor language
 * before that decision is made.  Full Line has no Sage language kit, so it
 * exits before scheduling model, native-server, or relevance-filter work.
 *
 * This is deliberately not an [InlineCompletionProvider]: Sage's index-backed
 * member list is exact semantic completion, while Full Line is probabilistic
 * next-text prediction.  Sending the member list through the latter would add
 * an asynchronous typing hot path without making `Q.` completion faster.
 */
class SageFullLineLanguageResolver : MLCompletionEditorLanguageResolver {
    override fun resolveCustomLanguageOrNull(editor: Editor): Language? =
        FileDocumentManager.getInstance().getFile(editor.document)
            ?.fileType
            ?.let(::languageFor)

    internal companion object {
        /** Small pure helper so the dialect decision remains testable. */
        fun languageFor(fileType: FileType): Language? =
            if (fileType === SageFileType.INSTANCE) SageLanguage.INSTANCE else null
    }
}
