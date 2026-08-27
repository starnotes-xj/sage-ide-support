package com.starnotesxj.sageide.completion

import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyReferenceExpression
import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SageApiDocumentationProviderTest : SagePluginTestBase() {
    fun testNativeDocumentationWinsOverIndexedDocumentation() {
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
            val resolved = requireNotNull(reference.reference?.resolve())
            assertTrue(resolved.containingFile.virtualFile?.name?.endsWith(".pyi") == true, resolved.toString())
            val provider = SageApiDocumentationProvider()
            assertNull(provider.getQuickNavigateInfo(resolved, reference))
            assertNull(provider.generateDoc(resolved, reference))
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
