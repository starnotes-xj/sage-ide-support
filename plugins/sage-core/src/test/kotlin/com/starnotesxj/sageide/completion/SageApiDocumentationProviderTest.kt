package com.starnotesxj.sageide.completion

import com.intellij.psi.PsiManager
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.PyDocStringOwner
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sagemath.sageapi.SageApiDocumentation
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeRef
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

    fun testPlainPythonFileDoesNotConsumeSageIndexButRendersLocalDocstrings() {
        val indexResource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")!!
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(indexResource.bufferedReader().use { SageApiIndexJsonReader.read(it.readText()) }),
        )
        try {
            myFixture.addFileToProject(
                "plain_native_docs.py",
                """
                    def documented(value: int) -> int:
                        '''Return the exact value for a normal Python file.'''
                        return value
                """.trimIndent(),
            )
            myFixture.configureByText("plain.py", "from plain_native_docs import documented\ndocumented<caret>")
            val reference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .lastOrNull { it.referencedName == "documented" }
            requireNotNull(reference)
            val resolved = requireNotNull(reference.reference.resolve())
            val documentation = requireNotNull(SageApiDocumentationProvider().generateDoc(resolved, reference))
            assertTrue("Return the exact value" in documentation, documentation)
            assertTrue("sage." !in documentation, documentation)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testOfflineStdlibDocumentationCoversTypeshedConstructors() {
        val builtinDocumentation = requireNotNull(PythonStdlibDocumentationService.documentationFor("len"))
        assertTrue("Return the number of items" in builtinDocumentation, builtinDocumentation)

        // The platform fixture does not mount its own typeshed SDK.  This
        // deliberately documentation-free stub has the same qualified PSI
        // shape as typeshed's ``itertools.product`` constructor.
        myFixture.addFileToProject(
            "itertools.pyi",
            """
                class product:
                    def __new__(cls, *iterables: object, repeat: int = 1) -> product:
                        '''Create and return a new object. See help(type) for accurate signature.'''
                        ...
            """.trimIndent(),
        )
        myFixture.configureByText("stdlib.py", "from itertools import product\nproduct<caret>([1, 2])")
        val reference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
            .lastOrNull { it.referencedName == "product" }
        requireNotNull(reference)
        val resolved = requireNotNull(reference.reference.resolve())
        val constructor = requireNotNull(
            (resolved as? PyClass)?.findMethodByName("__new__", false, TypeEvalContext.codeInsightFallback(project)),
        )
        val provider = SageApiDocumentationProvider()
        val documentation = requireNotNull(provider.generateDoc(constructor, reference))
        assertTrue("Cartesian product of input iterables" in documentation, documentation)
        assertTrue("Create and return a new object" !in documentation, documentation)
        assertTrue("docs.python.org" !in documentation, documentation)
        assertTrue(provider.getUrlFor(constructor, reference)?.isEmpty() == true)
    }

    fun testTypeshedPathRecoversStdlibNameWhenPsiQualifiedNameIsTransient() {
        // This uses the same path segment as the SDK bundled typeshed.  The
        // fixture's PSI qualified name is project-dependent (and therefore
        // deliberately not asserted); the provider must instead recover the
        // stable ``itertools.product`` key from the typeshed layout.
        myFixture.addFileToProject(
            "typeshed/stdlib/itertools.pyi",
            """
                class product:
                    def __new__(cls, *iterables: object, repeat: int = 1) -> product:
                        '''Create and return a new object. See help(type) for accurate signature.'''
                        ...
            """.trimIndent(),
        )
        val virtualFile = myFixture.findFileInTempDir("typeshed/stdlib/itertools.pyi")
        val typeshedFile = requireNotNull(PsiManager.getInstance(project).findFile(virtualFile))
        val product = requireNotNull(PsiTreeUtil.findChildOfType(typeshedFile, PyClass::class.java))
        val constructor = requireNotNull(
            product.findMethodByName("__new__", false, TypeEvalContext.codeInsightFallback(project)),
        )

        val provider = SageApiDocumentationProvider()
        val documentation = requireNotNull(provider.generateDoc(constructor, constructor))
        assertTrue("Cartesian product of input iterables" in documentation, documentation)
        assertTrue("Create and return a new object" !in documentation, documentation)
        assertTrue(provider.getUrlFor(constructor, constructor)?.isEmpty() == true)
    }

    fun testTypeshedPathRecoversBuiltinsConstructorDocumentation() {
        // ``zip`` is the builtin counterpart of the product regression from
        // the user report: its constructor record also carries object.__new__
        // prose, while the enclosing builtins.zip record has the useful text.
        myFixture.addFileToProject(
            "typeshed/stdlib/builtins.pyi",
            """
                class zip:
                    def __new__(cls, *iterables: object, strict: bool = False) -> zip:
                        '''Create and return a new object. See help(type) for accurate signature.'''
                        ...
            """.trimIndent(),
        )
        val virtualFile = myFixture.findFileInTempDir("typeshed/stdlib/builtins.pyi")
        val typeshedFile = requireNotNull(PsiManager.getInstance(project).findFile(virtualFile))
        val zip = requireNotNull(PsiTreeUtil.findChildOfType(typeshedFile, PyClass::class.java))
        val constructor = requireNotNull(
            zip.findMethodByName("__new__", false, TypeEvalContext.codeInsightFallback(project)),
        )

        val provider = SageApiDocumentationProvider()
        val documentation = requireNotNull(provider.generateDoc(constructor, constructor))
        assertTrue("The zip object yields n-length tuples" in documentation, documentation)
        assertTrue("Create and return a new object" !in documentation, documentation)
        assertTrue(provider.getUrlFor(constructor, constructor)?.isEmpty() == true)
    }

    fun testNativeDocumentationRejectsStaleTargetForListElement() {
        myFixture.addFileToProject(
            "image_module.py",
            """
                class Image:
                    def split(self):
                        '''WRONG Image.split documentation.'''
                        ...
            """.trimIndent(),
        )
        val imageVirtualFile = myFixture.findFileInTempDir("image_module.py")
        val imageFile = requireNotNull(PsiManager.getInstance(project).findFile(imageVirtualFile))
        val imageClass = requireNotNull(PsiTreeUtil.findChildOfType(imageFile, PyClass::class.java))
        val staleTarget = requireNotNull(
            imageClass.findMethodByName("split", false, TypeEvalContext.codeInsightFallback(project)),
        )

        myFixture.configureByText(
            "cipher.py",
            "intro: list[str] = ['prefix: 0011']\nflag_ciphertext = bytes.fromhex(intro[0].split(': ', 1)[1])",
        )
        val splitReference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
            .single { it.referencedName == "split" }
        val documentation = SageApiDocumentationProvider().generateDoc(staleTarget, splitReference)
        assertTrue(
            documentation == null || "WRONG Image.split documentation" !in documentation,
            documentation.orEmpty(),
        )
    }

    fun testNativeDocumentationUsesProvenReceiverTypeBeforePlatformTarget() {
        myFixture.addFileToProject(
            "image_module.py",
            """
                class Image:
                    def split(self):
                        '''WRONG Image.split documentation.'''
                        ...
            """.trimIndent(),
        )
        val imageVirtualFile = myFixture.findFileInTempDir("image_module.py")
        val imageFile = requireNotNull(PsiManager.getInstance(project).findFile(imageVirtualFile))
        val imageClass = requireNotNull(PsiTreeUtil.findChildOfType(imageFile, PyClass::class.java))
        val staleTarget = requireNotNull(
            imageClass.findMethodByName("split", false, TypeEvalContext.codeInsightFallback(project)),
        )

        myFixture.configureByText(
            "typed.py",
            """
                class Text:
                    def split(self):
                        '''RIGHT Text.split documentation.'''
                        ...
                value: Text = Text()
                value.split()
            """.trimIndent(),
        )
        val splitReference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
            .single { it.referencedName == "split" }
        val documentation = requireNotNull(
            SageApiDocumentationProvider().generateDoc(staleTarget, splitReference),
        )
        assertTrue("RIGHT Text.split documentation" in documentation, documentation)
        assertTrue("WRONG Image.split documentation" !in documentation, documentation)
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
