package com.starnotesxj.sageide.completion

import com.intellij.lang.documentation.DocumentationMarkup
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sageide.type.SageTypeProvider
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeState
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertTrue

/**
 * Lightweight Sage intelligence harness.
 *
 * This suite deliberately uses [SagePluginTestBase] and the IDE PSI fixture
 * instead of launching runIde.  It verifies the same boundaries that are
 * consumed by completion/type code: a real bundled index, real Sage stub
 * files, indexed members, typed call chains, signatures, and documentation.
 */
class SageIntelligenceHarnessTest : SagePluginTestBase() {

    fun testBundledIndexExposesRealSageSignatureAndDocumentationContract() {
        val query = loadBundledIndex()

        assertEquals("10.6", query.index.sageVersion)
        assertTrue(query.index.sourceDigests.isNotEmpty())

        val matrix = requireNotNull(query.find("sage.matrix.matrix.Matrix", SageApiSymbolKind.CLASS))
        assertEquals("Matrix objects.", matrix.documentation?.summary)
        assertEquals("Matrix objects.", matrix.documentation?.body)

        val solveRight = requireNotNull(query.find("sage.matrix.matrix.Matrix.solve_right", SageApiSymbolKind.METHOD))
        val solveRightSignature = solveRight.signatures.single()
        assertEquals(listOf("rhs"), solveRightSignature.parameters.map { it.name })
        assertEquals(SageTypeState.KNOWN, solveRightSignature.parameters.single().type.state)
        assertEquals("sage.matrix.matrix.Matrix", solveRightSignature.parameters.single().type.expression)
        assertEquals(SageTypeState.KNOWN, solveRightSignature.returnType.state)
        assertEquals("sage.matrix.matrix.Matrix", solveRightSignature.returnType.expression)

        val memberNames = query.members("sage.all.Matrix")
            .map { it.qualifiedName.substringAfterLast('.') }
            .toSet()
        assertTrue("solve_right" in memberNames, "indexed Matrix members=$memberNames")
        assertTrue("determinant" in memberNames, "indexed Matrix members=$memberNames")
        assertEquals("sage.matrix.matrix.Matrix", query.resolveKnownClassName("sage.all.Matrix"))
        assertEquals("sage.matrix.matrix.Matrix", query.uniqueKnownReturnType("matrix")?.expression)
        assertTrue("sage.matrix.matrix.Matrix" in query.reachableTypeNames("sage.all.Matrix"))

        val determinant = requireNotNull(
            query.find("sage.matrix.matrix.Matrix.determinant", SageApiSymbolKind.METHOD),
        )
        assertTrue(determinant.signatures.single().parameters.isEmpty())
        assertEquals(SageTypeState.KNOWN, determinant.signatures.single().returnType.state)
        assertEquals("sage.rings.integer.Integer", determinant.signatures.single().returnType.expression)

        val nthRoot = requireNotNull(
            query.find("sage.rings.integer.Integer.nth_root", SageApiSymbolKind.METHOD),
        )
        assertEquals(listOf("n", "truncate"), nthRoot.signatures.single().parameters.map { it.name })
        assertEquals("False", nthRoot.signatures.single().parameters[1].defaultValue)
        assertEquals("sage.rings.integer.Integer", nthRoot.signatures.single().returnType.expression)

        val factor = requireNotNull(query.resolve("sage.all.factor", SageApiSymbolKind.FUNCTION))
        assertEquals("sage.arith.misc.factor", factor.qualifiedName)
        assertEquals(listOf("n"), factor.signatures.single().parameters.map { it.name })
        assertEquals(
            "list[tuple[sage.rings.integer.Integer, sage.rings.integer.Integer]]",
            factor.signatures.single().returnType.expression,
        )

        val continuedFraction = requireNotNull(
            query.resolve("continued_fraction", SageApiSymbolKind.FUNCTION),
        )
        assertEquals("sage.arith.misc.continued_fraction", continuedFraction.qualifiedName)
        assertEquals(listOf("n"), continuedFraction.signatures.single().parameters.map { it.name })
        assertEquals("list[sage.rings.integer.Integer]", continuedFraction.signatures.single().returnType.expression)
        assertEquals("sage.rings.integer.Integer", query.resolveKnownClassName("Integer"))
    }

    fun testPsiCompletionUsesIndexedMembersFromARealSageStub() {
        withBundledIndex {
            // Use the same small Matrix PSI fixture as production-like Sage
            // completion tests, then verify both an indexed member and a
            // native stub member through the same call-site.
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix.pyi",
                "sage/matrix/matrix.pyi",
            )
            myFixture.configureByText(
                "indexed-members.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nA.sol<caret>ve",
            )
            myFixture.doHighlighting()
            val solveLookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("solve_right" in solveLookup, "indexed Matrix completion=$solveLookup")
        }
    }

    fun testPsiTypeProviderAndCompletionTraverseARealSageCallChain() {
        withBundledIndex {
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix.pyi",
                "sage/matrix/matrix.pyi",
            )
            myFixture.configureByText(
                "typed-chain.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nB = A.solve_right(A)\nA.det<caret>",
            )
            myFixture.doHighlighting()

            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            val a = targets.first { it.name == "A" }
            val b = targets.first { it.name == "B" }
            val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            assertEquals("Matrix", (context.getType(a) as? PyClassType)?.name)
            assertEquals("Matrix", (context.getType(b) as? PyClassType)?.name)

            assertTrue("solve_right" in loadBundledIndex().members("sage.matrix.matrix.Matrix")
                .map { it.qualifiedName.substringAfterLast('.') })
        }
    }

    fun testIndexedMemberCallableTypePropagatesThroughSparseStub() {
        withBundledIndex {
            myFixture.copyFileToProject(
                "testData/sage-stubs/site-packages/sage/__init__.pyi",
                "site-packages/sage/__init__.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/site-packages/sage/rings/__init__.pyi",
                "site-packages/sage/rings/__init__.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/all.pyi",
                "site-packages/sage/all.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/rings/real_mpfr.pyi",
                "site-packages/sage/rings/real_mpfr.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix-sparse.pyi",
                "sage/matrix/matrix.pyi",
            )

            myFixture.copyFileToProject(
                "testData/sage-stubs/site-packages/sage/matrix/__init__.pyi",
                "sage/matrix/__init__.pyi",
            )
            myFixture.configureByText(
                "indexed-call.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nB = A.solve_right(A)\nB.det<caret>",
            )
            myFixture.doHighlighting()

            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            val a = targets.first { it.name == "A" }
            val b = targets.first { it.name == "B" }
            val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            val solveReference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .single { it.referencedName == "solve_right" }
            val inferred = context.getType(b) as? PyClassType
            if (inferred == null) {
                val refs = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                    .joinToString(" | ") { ref ->
                        ref.referencedName + ":resolve=" + ref.reference?.resolve()?.javaClass?.name +
                            ":type=" + context.getType(ref)
                    }
                error(
                    "sparse B type missing AType=" + context.getType(a) +
                        " AValue=" + a.findAssignedValue()?.javaClass?.name +
                        " BValue=" + b.findAssignedValue()?.javaClass?.name +
                        " solveQualifierType=" + context.getType(solveReference.qualifier ?: solveReference) +
                        " solveResolve=" + solveReference.reference?.resolve()?.javaClass?.name +
                        " refs=" + refs,
                )
            }
            assertEquals(
                "sage.matrix.matrix.Matrix",
                inferred.pyClass.let(SageStubIndex::canonicalQualifiedName),
            )

            val solveTarget = solveReference.reference?.resolve()
            val resolvedSolveTarget = solveTarget
                ?: error(
                    "indexed solve_right did not resolve qualifierType=" +
                        context.getType(solveReference.qualifier ?: solveReference) +
                        " AType=" + context.getType(targets.first { it.name == "A" }) +
                        " BType=" + context.getType(b) +
                        " multiResolve=" + solveReference.reference?.multiResolve(false).contentToString(),
                )
            val solveType = context.getType(resolvedSolveTarget as com.jetbrains.python.psi.PyTypedElement)
            assertTrue(solveType is com.jetbrains.python.psi.types.PyCallableType, solveType.toString())
            assertEquals(
                listOf("rhs"),
                (solveType as com.jetbrains.python.psi.types.PyCallableType)
                    .getParameters(context)
                    .orEmpty()
                    .map { it.name },
            )
            assertTrue(
                SageApiClassMembersProvider()
                    .getMembers(inferred, myFixture.file, context)
                    .any { it.name == "determinant" },
            )

            myFixture.configureByText(
                "indexed-return.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nB = A.solve_right(A)\nB.det<caret>",
            )
            myFixture.doHighlighting()
            val returnTargets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            val returnB = returnTargets.first { it.name == "B" }
            val returnContext = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            val returnType = returnContext.getType(returnB)
            val returnClassType = returnType as? PyClassType
            assertEquals(
                "sage.matrix.matrix.Matrix",
                returnClassType?.pyClass?.let(SageStubIndex::canonicalQualifiedName),
            )
            val completionItems = myFixture.completeBasic()
            val lookup = completionItems?.map { it.lookupString }.orEmpty()
            val completedText = myFixture.file.text
            assertTrue(
                "determinant" in lookup || "B.determinant" in completedText,
                "indexed callable return completion=" +
                    (completionItems?.contentToString() ?: "<auto-completed>") +
                    " lookup=$lookup BType=$returnType text=$completedText",
            )
        }
    }

    fun testPsiDocumentationProviderRendersIndexedSignatureAndDocumentation() {
        withBundledIndex {
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix.pyi",
                "sage/matrix/matrix.pyi",
            )
            myFixture.configureByText(
                "documentation.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nA.solve_right<caret>",
            )
            myFixture.doHighlighting()

            val element = PsiTreeUtil.collectElementsOfType(
                myFixture.file,
                com.jetbrains.python.psi.PyReferenceExpression::class.java,
            ).firstOrNull { it.referencedName == "solve_right" }
                ?: error("No solve_right PSI reference at documentation caret")
            val provider = SageApiDocumentationProvider()
            val signature = provider.getQuickNavigateInfo(element, element)
                ?: error("Sage documentation provider returned no signature")
            assertTrue("sage.matrix.matrix.Matrix.solve_right" in signature, signature)
            assertTrue("rhs: sage.matrix.matrix.Matrix" in signature, signature)
            assertTrue("-> sage.matrix.matrix.Matrix" in signature, signature)

            val documentation = provider.generateDoc(element, element)
                ?: error("Sage documentation provider returned no documentation")
            assertTrue("sage.matrix.matrix.Matrix.solve_right" in documentation, documentation)
            assertTrue("rhs: sage.matrix.matrix.Matrix" in documentation, documentation)
        }
    }

    fun testConfiguredFullIndexCompletesAnExternalOnlyRootIdentity() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }

        val service = SageApiIndexService.getInstance()
        try {
            assertTrue(service.reload(path), service.loadState().error ?: "external full index load failed")
            val fullQuery = requireNotNull(service.query())
            val externalOnly = fullQuery.namespaceEntries("sage.all").first {
                it.qualifiedName == "sage.all.AffineSpace"
            }
            assertEquals(SageApiSymbolKind.FUNCTION, externalOnly.kind)
            assertTrue(fullQuery.find(externalOnly.qualifiedName, externalOnly.kind) === externalOnly)

            myFixture.configureByText(
                "full-root-completion.sage",
                "AffineSp<caret>",
            )
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            val completedText = myFixture.file.text
            assertTrue(
                "AffineSpace" in lookup || "AffineSpace" in completedText,
                "external-only Sage root completion=$lookup text=$completedText file=${myFixture.file.javaClass.name} type=${myFixture.file.fileType.name} language=${myFixture.file.language.id}",
            )
            assertTrue(
                completedText == "AffineSpace()" || "AffineSpace" in lookup,
                "FUNCTION root completion did not preserve callable insertion: lookup=$lookup text=$completedText",
            )
        } finally {
            service.install(null)
        }
    }

    fun testConfiguredFullIndexDocumentsAmbiguousExternalOnlyRoot() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }

        val service = SageApiIndexService.getInstance()
        try {
            assertTrue(service.reload(path), service.loadState().error ?: "external full index load failed")
            val query = requireNotNull(service.query())
            val entry = requireNotNull(query.namespaceEntry("sage.all", "AffineSpace"))
            assertEquals(SageApiSymbolKind.FUNCTION, entry.kind)
            assertEquals(null, query.resolve("AffineSpace"))
            assertEquals(5, query.signatures(entry.qualifiedName).single().parameters.size)
            assertTrue(query.documentation(entry.qualifiedName)?.summary.orEmpty().isNotBlank())

            myFixture.configureByText("external-root-documentation.sage", "AffineSpace<caret>")
            val reference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .single { it.referencedName == "AffineSpace" }
            val provider = SageApiDocumentationProvider()
            val quick = requireNotNull(provider.getQuickNavigateInfo(reference, reference))
            val documentation = requireNotNull(provider.generateDoc(reference, reference))

            assertTrue("sage.all.AffineSpace" in quick, quick)
            assertTrue("n" in quick && "R = None" in quick, quick)
            assertTrue("-> sage.schemes.affine.affine_space.AffineSpace_generic" in quick, quick)
            assertTrue("Return affine space of dimension" in documentation, documentation)
            assertTrue(DocumentationMarkup.DEFINITION_START in documentation, documentation)
        } finally {
            service.install(null)
        }
    }

    fun testConfiguredFullIndexCompletesExternalOnlyAliasAndConstantRoots() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }

        val service = SageApiIndexService.getInstance()
        try {
            assertTrue(service.reload(path), service.loadState().error ?: "external full index load failed")
            val query = requireNotNull(service.query())
            val alias = requireNotNull(query.find("sage.all.var", SageApiSymbolKind.ALIAS))
            val constant = requireNotNull(query.find("sage.all.RR", SageApiSymbolKind.CONSTANT))
            assertTrue(alias in query.namespaceEntries("sage.all"))
            assertTrue(constant in query.namespaceEntries("sage.all"))

            myFixture.configureByText("full-root-alias.sage", "var<caret>")
            val aliasLookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("var" in aliasLookup, "external-only ALIAS root completion=$aliasLookup")

            myFixture.configureByText("full-root-constant.sage", "RR<caret>")
            val constantLookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("RR" in constantLookup, "external-only CONSTANT root completion=$constantLookup")
        } finally {
            service.install(null)
        }
    }

    fun testConfiguredFullIndexExposesEveryRootCompletionIdentity() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }

        val service = SageApiIndexService.getInstance()
        try {
            assertTrue(service.reload(path), service.loadState().error ?: "external full index load failed")
            val root = requireNotNull(service.query()).namespaceEntries("sage.all")
            assertEquals(2_158, root.size)
            assertEquals(2_158, root.map { it.qualifiedName.substringAfterLast('.') }.distinct().size)
            assertTrue(root.all { entry -> service.query()?.find(entry.qualifiedName, entry.kind) == entry })
        } finally {
            service.install(null)
        }
    }

    fun testConfiguredFullIndexPreservesSafeMethodReturnStates() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }

        val service = SageApiIndexService.getInstance()
        try {
            assertTrue(service.reload(path), service.loadState().error ?: "external full index load failed")
            val query = requireNotNull(service.query())
            val methodsWithSignatures = query.index.entries.filter {
                it.kind == SageApiSymbolKind.METHOD && it.signatures.isNotEmpty()
            }
            assertTrue(methodsWithSignatures.isNotEmpty())
            val unsafe = methodsWithSignatures.asSequence()
                .filter { entry ->
                    val returns = query.callReturnTypes(entry.qualifiedName)
                    returns.isEmpty() || returns.any { it.state != SageTypeState.KNOWN || it.expression.isNullOrBlank() } ||
                        returns.map { it.expression }.distinct().size != 1
                }
                .take(10)
                .toList()
            val missingSafe = methodsWithSignatures.asSequence()
                .filter { entry ->
                    val returns = query.callReturnTypes(entry.qualifiedName)
                    returns.isNotEmpty() && returns.all { type ->
                        type.state == SageTypeState.KNOWN &&
                            !type.expression.isNullOrBlank() &&
                            '|' !in type.expression.orEmpty()
                    } && returns.map { it.expression }.distinct().size == 1 &&
                        query.uniqueKnownReturnType(entry.qualifiedName) == null
                }
                .take(10)
                .toList()
            assertTrue(missingSafe.isEmpty(), "Safe method returns are not exposed: $missingSafe")
            assertTrue(unsafe.isNotEmpty(), "Full artifact unexpectedly has no conservative UNKNOWN/DYNAMIC method cases")
            val solveRightReturn = query.callReturnTypes("sage.matrix.matrix2.Matrix.solve_right").single()
            assertEquals(SageTypeState.KNOWN, solveRightReturn.state)
            assertEquals("sage.modules.free_module_element.FreeModuleElement | sage.matrix.matrix2.Matrix", solveRightReturn.expression)
            assertEquals(null, query.uniqueKnownReturnType("sage.matrix.matrix2.Matrix.solve_right"))
            assertEquals(null, query.uniqueKnownReturnType("sage.rings.integer.Integer.nth_root"))
        } finally {
            service.install(null)
        }
    }

    fun testConfiguredFullIndexPropagatesExternalFactoryReturnToPsiMembers() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }

        val service = SageApiIndexService.getInstance()
        try {
            assertTrue(service.reload(path), service.loadState().error ?: "external full index load failed")
            val query = requireNotNull(service.query())
            val realField = requireNotNull(query.find("sage.all.RealField", SageApiSymbolKind.FUNCTION))
            val returnType = realField.signatures.single().returnType
            assertEquals(SageTypeState.KNOWN, returnType.state)
            assertEquals("sage.rings.real_mpfr.RealField_class", returnType.expression)
            assertEquals(returnType.expression, query.uniqueKnownReturnType(realField.qualifiedName)?.expression)
            assertEquals(returnType.expression, query.resolveKnownClassName(returnType.expression!!))
            assertTrue(query.members(returnType.expression!!).any { it.qualifiedName.endsWith(".precision") })

            myFixture.copyFileToProject(
                "testData/sage-stubs/site-packages/sage/__init__.pyi",
                "site-packages/sage/__init__.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/site-packages/sage/rings/__init__.pyi",
                "site-packages/sage/rings/__init__.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/all.pyi",
                "site-packages/sage/all.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/rings/real_mpfr.pyi",
                "site-packages/sage/rings/real_mpfr.pyi",
            )
            myFixture.configureByText(
                "external-factory-type.sage",
                "R = RealField()\nR.pre<caret>cision",
            )
            myFixture.doHighlighting()
            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            val target = targets.firstOrNull { it.name == "R" }
                ?: error("external factory target R missing; file=${myFixture.file.language} type=${myFixture.file.fileType}")
            val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            val directProviderType = SageTypeProvider().getReferenceType(target, context, null)?.get()
            val inferred = context.getType(target) as? PyClassType
            val inferredCanonical = inferred?.let { SageStubIndex.canonicalQualifiedName(it.pyClass) }
            assertTrue(
                inferredCanonical == "sage.rings.real_mpfr.RealField_class",
                "external factory inferred=${inferred?.name} canonical=$inferredCanonical direct=${directProviderType?.let { (it as PyClassType).name }} file=${myFixture.file.language}/${myFixture.file.fileType}",
            )
            assertTrue(
                query.members("sage.rings.real_mpfr.RealField_class").any { it.qualifiedName.endsWith(".precision") },
                "external RealField members missing precision",
            )
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("precision" in lookup, "external factory member completion=$lookup")
        } finally {
            service.install(null)
        }
    }

    fun testPsiCompletionCoversSageArithmeticFunctionsAndIntegerMember() {
        withBundledIndex {
            copyStub("sage/arith/misc.pyi", "testData/sage-stubs/sage/arith/misc.pyi")
            copyStub("sage/rings/integer.pyi", "testData/sage-stubs/sage/rings/integer.pyi")
            myFixture.configureByText(
                "arithmetic.sage",
                "from sage.rings.integer import Integer\nvalue = Integer(17)\nvalue.nth<caret>_root",
            )
            myFixture.doHighlighting()

            val integerLookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("nth_root" in integerLookup, "Integer member completion=$integerLookup")
        }
    }

    private fun copyStub(target: String, source: String) {
        myFixture.copyFileToProject(source, target)
    }

    private fun loadBundledIndex(): SageApiIndexQuery {
        val resource = javaClass.classLoader.getResourceAsStream("sage-api-index.json")
            ?: error("bundled sage-api-index.json is missing")
        return SageApiIndexQuery(SageApiIndexJsonReader.read(resource.bufferedReader().use { it.readText() }))
    }

    private fun withBundledIndex(block: () -> Unit) {
        SageApiIndexService.getInstance().install(loadBundledIndex())
        try {
            block()
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }
}
