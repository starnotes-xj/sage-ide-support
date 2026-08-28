package com.starnotesxj.sageide.completion

import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyDocStringOwner
import com.jetbrains.python.psi.PyReferenceExpression
import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sagemath.sageapi.SageApiDocumentation
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeRef
import kotlin.test.assertNull
import kotlin.test.assertTrue

class SageApiDocumentationProviderTest : SagePluginTestBase() {
    fun testSageIndexedDocumentationWinsWithoutLocalPythonSdk() {
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
            val quick = provider.getQuickNavigateInfo(resolved, reference)
            assertTrue(quick?.contains("sage.matrix.matrix.Matrix") == true, quick.orEmpty())
            val doc = provider.generateDoc(resolved, reference)
            assertTrue(doc?.contains("sage.matrix.matrix.Matrix") == true, doc.orEmpty())
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

    fun testNativePythonDocumentationAvoidsRemoteSdkFormatter() {
        myFixture.addFileToProject(
            "native_docs.py",
            """
                def randint(a: int, b: int) -> int:
                    '''Return an integer.

                    Parameters:
                    - ``a`` -- lower bound.

                    Returns:
                    ``int`` -- random value.
                    '''
                    return a
            """.trimIndent(),
        )
        myFixture.configureByText(
            "native.sage",
            "from native_docs import randint\nrandint<caret>",
        )
        val reference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
            .lastOrNull { it.referencedName == "randint" }
        requireNotNull(reference)
        val resolved = requireNotNull(reference.reference.resolve())
        assertTrue(resolved is PyDocStringOwner, resolved.toString())

        val provider = SageApiDocumentationProvider()
        val quick = requireNotNull(provider.getQuickNavigateInfo(resolved, reference))
        assertTrue(quick.contains("randint"), "quick=$quick resolved=$resolved context=${reference.containingFile.name}")
        assertTrue(quick.contains("<span"), "semantic quick info=$quick")
        val quickText = quick.replace(Regex("<[^>]+>"), "")
        assertTrue("def native_docs.randint(a: int, b: int) -> int" in quickText, quickText)
        val doc = requireNotNull(provider.generateDoc(resolved, reference))
        assertTrue(doc.contains("Return an integer."), doc)
        assertTrue(doc.contains("<table class='sections'>"), doc)
        assertTrue("QDOC.python.3.sdk.needed.to.render.docstrings" !in doc, doc)
    }

    fun testIndexedDocumentationPreservesSectionsAndRendersFencedCode() {
        val entry = SageApiEntry(
            qualifiedName = "sage.demo.log",
            kind = SageApiSymbolKind.METHOD,
            signatures = listOf(
                SageApiSignature(
                    parameters = listOf(SageApiParameter("base", SageTypeRef.known("Integer"))),
                    returnType = SageTypeRef.known("Integer"),
                ),
            ),
            documentation = SageApiDocumentation(
                summary = "Compute a discrete logarithm.",
                body = """
                    Parameters:
                    - ``base`` -- the logarithm base.

                    Returns:
                    ``Integer`` -- the discrete logarithm.

                    Examples:
                    ```sage
                    P.log(G)
                    G.log(P)
                    ```
                """.trimIndent(),
            ),
        )
        val renderDocumentation = SageApiDocumentationProvider::class.java
            .getDeclaredMethod("renderDocumentation", SageApiEntry::class.java)
            .apply { isAccessible = true }
        val html = renderDocumentation.invoke(SageApiDocumentationProvider(), entry) as String

        assertTrue("<table class='sections'>" in html, html)
        assertTrue("class='section'" in html, html)
        assertTrue("sage.demo.log" in html, html)
        assertTrue("<code>base</code>" in html, html)
        assertTrue("<pre><code>P.log(G)\nG.log(P)</code></pre>" in html, html)
        assertTrue("```" !in html, html)
    }
}
