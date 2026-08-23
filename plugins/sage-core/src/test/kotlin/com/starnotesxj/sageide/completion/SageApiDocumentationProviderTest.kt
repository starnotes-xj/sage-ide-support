package com.starnotesxj.sageide.completion

import com.intellij.lang.documentation.DocumentationMarkup
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyReferenceExpression
import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import kotlin.test.assertTrue

class SageApiDocumentationProviderTest : SagePluginTestBase() {
    fun testIndexedDocumentationIncludesSignatureAndBody() {
        val indexResource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")!!
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(indexResource.bufferedReader().use { SageApiIndexJsonReader.read(it.readText()) }),
        )
        try {
            myFixture.copyFileToProject("testData/sage-stubs/sage/matrix/matrix.pyi", "sage/matrix/matrix.pyi")
            myFixture.configureByText(
                "matrix.sage",
                "from sage.matrix.matrix import Matrix\nMatrix<caret>",
            )
            val reference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .firstOrNull { it.referencedName == "Matrix" }
            requireNotNull(reference)
            val provider = SageApiDocumentationProvider()
            val quick = provider.getQuickNavigateInfo(reference, reference).orEmpty()
            val doc = provider.generateDoc(reference, reference).orEmpty()
            assertTrue(quick.contains("Matrix"), quick)
            assertTrue(doc.contains("Matrix"), doc)
            assertTrue(doc.contains("Matrix objects."), doc)
            assertTrue(doc.contains(DocumentationMarkup.DEFINITION_START), doc)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testPlainPythonFileDoesNotConsumeSageIndex() {
        val indexResource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")!!
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(indexResource.bufferedReader().use { SageApiIndexJsonReader.read(it.readText()) }),
        )
        try {
            myFixture.configureByText("plain.py", "solve_right<caret>")
            val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .firstOrNull()
            requireNotNull(target)
            assertTrue(SageApiDocumentationProvider().generateDoc(target, target) == null)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }
}
