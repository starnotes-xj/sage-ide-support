package com.starnotesxj.sageide.completion

import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndex
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind

class SageCompletionTest : SagePluginTestBase() {

    fun testIndexedMatrixMethodCompletes() {
        val indexResource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")!!
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(SageApiIndexJsonReader.read(indexResource.bufferedReader().use { it.readText() })),
        )
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.configureByText(
                "matrix.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nA.sol<caret>ve",
            )
            myFixture.doHighlighting()
            val target = myFixture.file.text.substringBefore("\nA =")
            val targetExpression = com.intellij.psi.util.PsiTreeUtil.collectElementsOfType(
                myFixture.file,
                com.jetbrains.python.psi.PyTargetExpression::class.java,
            ).first { it.name == "A" }
            val inferred = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(
                myFixture.project, myFixture.file,
            ).getType(targetExpression)

            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("matrix type=$target inferred=$inferred completion=$lookup", "solve_right" in lookup)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testSageRootCandidatesAreNotInjectedInsideString() {
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(
                SageApiIndex(
                    "10.9",
                    "3.13",
                    listOf(SageApiEntry("sage.all.EllipticCurve", SageApiSymbolKind.CLASS)),
                ),
            ),
        )
        try {
            myFixture.configureByText("string.sage", "message = 'Ell<caret>'\n")
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertFalse("Sage root completion leaked into a string: $lookup", "EllipticCurve" in lookup)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }
}
