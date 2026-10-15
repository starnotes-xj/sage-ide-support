package com.starnotesxj.sageide.highlight

import com.starnotesxj.sageide.SagePluginTestBase
import com.intellij.openapi.application.ReadAction
import com.intellij.openapi.progress.ProgressManager
import com.intellij.openapi.progress.util.ProgressIndicatorBase
import java.util.concurrent.Callable

class SageXorInspectionTest : SagePluginTestBase() {

    fun testOnlyReportsUnambiguousByteXor() {
        myFixture.configureByText(
            "xor.sage",
            """
                byte_xor = b"a" <error descr="In Sage, ^ is exponentiation (preparsed to **), not XOR. Use ^^ for bitwise XOR.">^</error> b"b"
                value = b"a"
                value <error descr="In Sage, ^= is power-assignment (preparsed to **=), not XOR. Use ^^= for bitwise XOR.">^=</error> b"b"
                power = 2^8
            """.trimIndent(),
        )
        myFixture.enableInspections(SageXorInspection())

        myFixture.checkHighlighting()
    }

    fun testBinaryOperatorQuickFixUsesSageXorSpelling() {
        myFixture.configureByText("xor.sage", "result = b\"a\" <caret>^ b\"b\"")
        myFixture.enableInspections(SageXorInspection())

        myFixture.launchAction(myFixture.findSingleIntention("Replace ^ with ^^"))

        assertEquals("result = b\"a\" ^^ b\"b\"", myFixture.file.text)
    }

    fun testAugmentedAssignmentQuickFixUsesSageXorSpelling() {
        myFixture.configureByText("xor.sage", "value = b\"a\"\nvalue <caret>^= b\"b\"")
        myFixture.enableInspections(SageXorInspection())

        myFixture.launchAction(myFixture.findSingleIntention("Replace ^= with ^^="))

        assertEquals("value = b\"a\"\nvalue ^^= b\"b\"", myFixture.file.text)
    }

    fun testBatchPreviewPlansAllEditsWithoutOffsetDrift() {
        val preview = SageBatchFixPlanner.plan(
            "^ + ^=",
            listOf(
                SageTextReplacement(0, 1, "^", "^^"),
                SageTextReplacement(4, 6, "^=", "^^="),
            ),
        )

        assertNotNull(preview)
        assertEquals("^^ + ^^=", preview!!.afterText)
        assertEquals(2, preview.replacements.size)
    }

    fun testBatchPreviewRejectsStaleOrOverlappingEdits() {
        assertNull(SageBatchFixPlanner.plan("changed", listOf(SageTextReplacement(0, 1, "^", "^^"))))
        assertNull(
            SageBatchFixPlanner.plan(
                "^ ",
                listOf(
                    SageTextReplacement(0, 1, "^", "^^"),
                    SageTextReplacement(0, 2, "^ ", "^^ "),
                ),
            ),
        )
    }

    fun testProjectBatchPreviewPlansSelectedFilesInStableOrder() {
        val preview = SageBatchFixPlanner.planFiles(
            listOf(
                SageBatchFixInput("z.sage", "^", listOf(SageTextReplacement(0, 1, "^", "^^"))),
                SageBatchFixInput("no-fix.sage", "2^8", emptyList()),
                SageBatchFixInput("a.sage", "^", listOf(SageTextReplacement(0, 1, "^", "^^"))),
            ),
        )

        assertNotNull(preview)
        assertEquals(listOf("a.sage", "z.sage"), preview!!.files.map(SageBatchFileFixPreview::path))
        assertEquals(listOf("^^", "^^"), preview.files.map(SageBatchFileFixPreview::afterText))
        assertEquals(2, preview.replacementCount)
    }

    fun testCurrentFilePreviewUsesInspectionFixesAndLeavesSagePowersAlone() {
        val source = "byte_xor = b\"a\" ^ b\"b\"\npower = 2^8\n"
        val file = myFixture.configureByText("preview.sage", source)
        val indicator = ProgressIndicatorBase()
        var preview: SageBatchFixPreview? = null

        ProgressManager.getInstance().runProcess(
            Runnable {
                preview = ReadAction.nonBlocking(Callable {
                    SageBatchFixPreviewFactory.forFile(myFixture.project, file)
                }).wrapProgress(indicator).executeSynchronously()
            },
            indicator,
        )

        assertNotNull(preview)
        val actualPreview = preview!!
        assertEquals(source, actualPreview.beforeText)
        assertEquals("byte_xor = b\"a\" ^^ b\"b\"\npower = 2^8\n", actualPreview.afterText)
        assertEquals(1, actualPreview.replacements.size)
    }

    fun testSelectedFilesPreviewCollectsOnlyFilesWithSafeFixes() {
        val later = myFixture.addFileToProject("z-preview.sage", "byte_xor = b\"z\" ^ b\"z\"")
        val noFix = myFixture.addFileToProject("m-preview.sage", "power = 2^8")
        val earlier = myFixture.addFileToProject("a-preview.sage", "byte_xor = b\"a\" ^ b\"a\"")
        val indicator = ProgressIndicatorBase()
        var preview: SageProjectBatchFixPreview? = null

        ProgressManager.getInstance().runProcess(
            Runnable {
                preview = ReadAction.nonBlocking(Callable {
                    SageBatchFixPreviewFactory.forFiles(myFixture.project, listOf(later, noFix, earlier))
                }).wrapProgress(indicator).executeSynchronously()
            },
            indicator,
        )

        assertNotNull(preview)
        val actualPreview = preview!!
        assertEquals(listOf("a-preview.sage", "z-preview.sage"), actualPreview.files.map { it.path.substringAfterLast('/') })
        assertEquals(2, actualPreview.replacementCount)
        assertTrue(actualPreview.files.all { "^^" in it.afterText })
    }

    fun testProjectBatchPreviewRejectsUnsafeOrAmbiguousInputs() {
        assertNull(
            SageBatchFixPlanner.planFiles(
                listOf(
                    SageBatchFixInput("safe.sage", "^", listOf(SageTextReplacement(0, 1, "^", "^^"))),
                    SageBatchFixInput("stale.sage", "changed", listOf(SageTextReplacement(0, 1, "^", "^^"))),
                ),
            ),
        )
        assertNull(
            SageBatchFixPlanner.planFiles(
                listOf(
                    SageBatchFixInput("duplicate.sage", "^", listOf(SageTextReplacement(0, 1, "^", "^^"))),
                    SageBatchFixInput("duplicate.sage", "^", listOf(SageTextReplacement(0, 1, "^", "^^"))),
                ),
            ),
        )
    }
}
