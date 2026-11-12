package com.starnotesxj.sageide.inline

import com.intellij.codeInsight.inline.completion.InlineCompletionEvent
import com.intellij.codeInsight.inline.completion.suggestion.InlineCompletionSuggestion
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.application.readAction
import com.intellij.openapi.project.DumbService
import com.intellij.openapi.project.DumbServiceImpl
import com.intellij.psi.PsiDocumentManager
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sageide.completion.SageApiIndexService
import com.starnotesxj.sageide.sugar.SageReferenceResolveProvider
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sageide.type.SageIndexedTypeResolver
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndex
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeRef
import kotlinx.coroutines.runBlocking

class SageInlineDumbModeTest : SagePluginTestBase() {
    private lateinit var query: SageApiIndexQuery

    override fun runInDispatchThread(): Boolean = false

    override fun setUp() {
        super.setUp()
        val field = "sage.rings.finite_rings.finite_field_base.FiniteField"
        query = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    SageApiEntry(field, SageApiSymbolKind.CLASS),
                    SageApiEntry(
                        "sage.all.GF",
                        SageApiSymbolKind.FUNCTION,
                        signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(field))),
                    ),
                    SageApiEntry("$field.xy", SageApiSymbolKind.METHOD),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(query)
    }

    override fun tearDown() {
        try {
            SageApiIndexService.getInstance().install(null)
        } finally {
            super.tearDown()
        }
    }

    fun testInlineScoringSkipsIndexAccessInDumbMode() = runBlocking {
        configureInlineFile()
        val service = SageInlinePredictionService.getInstance(project)
        assertEquals("xy", readAction { service.prepareScoringRequest(myFixture.file, myFixture.caretOffset) }?.prefix)
        val request = requireNotNull(
            InlineCompletionEvent.DirectCall(myFixture.editor, myFixture.editor.caretModel.currentCaret).toRequest(),
        )

        inDumbMode("Sage inline completion test") {
            assertTrue(readAction { DumbService.isDumb(project) })
            assertNull(readAction { service.prepareScoringRequest(myFixture.file, myFixture.caretOffset) })
            val suggestion = SageInlineCompletionProvider().getSuggestionDebounced(request)
            assertSame(InlineCompletionSuggestion.Empty, suggestion)
        }
    }

    fun testSageResolutionEntryPointsReturnEmptyInDumbMode() = runBlocking {
        configureInlineFile()
        val (reference, target) = readAction {
            val references = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            references.first { it.referencedName == "GF" && it.qualifier == null } to targets.first { it.name == "P" }
        }

        inDumbMode("Sage resolution test") {
            assertTrue(readAction { DumbService.isDumb(project) })
            assertTrue(
                readAction {
                    SageReferenceResolveProvider()
                        .resolveName(reference, TypeEvalContext.codeInsightFallback(project))
                        .isEmpty()
                },
            )
            assertTrue(readAction { SageIndexedTypeResolver.ownersForExpression(reference, query).isEmpty() })
            assertTrue(readAction { SageIndexedTypeResolver.ownersForTarget(target, query).isEmpty() })
            assertNull(readAction { SageStubIndex.findDeclaration(project, "SageDumbModeMissingName") })
            assertNull(readAction { SageStubIndex.findClassByCanonicalName(project, "sage.test.DumbModeMissing") })
        }
    }

    private fun configureInlineFile() {
        ApplicationManager.getApplication().invokeAndWait {
            myFixture.configureByText("inline-dumb-mode.sage", "P = GF(11)\nP.xy<caret>")
            PsiDocumentManager.getInstance(project).commitAllDocuments()
        }
    }

    private suspend fun inDumbMode(activityName: String, block: suspend () -> Unit) {
        DumbServiceImpl.getInstance(project).runInDumbMode(activityName) { block() }
    }
}
