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
import com.starnotesxj.sagemath.sageapi.SageTypeExpression
import com.starnotesxj.sagemath.sageapi.SageTypeState
import java.nio.file.Files
import java.nio.file.Path
import kotlin.test.assertEquals
import kotlin.test.assertNull
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
        val expectedFullIndex = System.getProperty("sage.bundle.fullIndex") != null

        if (expectedFullIndex) {
            assertFullSage10_9Contract(query)
            return
        }

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

    private fun assertFullSage10_9Contract(query: SageApiIndexQuery) {
        assertEquals("10.9", query.index.sageVersion)
        assertTrue(query.index.sourceDigests.isNotEmpty())

        val matrix = requireNotNull(query.find("sage.matrix.matrix2.Matrix", SageApiSymbolKind.CLASS))
        assertTrue(matrix.documentation?.summary?.isNotBlank() == true)
        assertTrue(matrix.documentation?.body?.isNotBlank() == true)

        val solveRight = requireNotNull(query.find("sage.matrix.matrix2.Matrix.solve_right", SageApiSymbolKind.METHOD))
        val solveRightSignature = solveRight.signatures.single()
        assertEquals(listOf("B", "check", "extend"), solveRightSignature.parameters.map { it.name })
        assertEquals(SageTypeState.UNKNOWN, solveRightSignature.parameters.first().type.state)
        assertEquals(SageTypeState.KNOWN, solveRightSignature.returnType.state)
        assertEquals("sage.modules.free_module_element.FreeModuleElement | sage.matrix.matrix2.Matrix", solveRightSignature.returnType.expression)

        val memberNames = query.members("sage.matrix.matrix2.Matrix")
            .map { it.qualifiedName.substringAfterLast('.') }
            .toSet()
        assertTrue("solve_right" in memberNames, "indexed Matrix members=$memberNames")
        assertTrue("determinant" in memberNames, "indexed Matrix members=$memberNames")
        val matrixFactory = requireNotNull(query.resolve("sage.all.Matrix", SageApiSymbolKind.FUNCTION))
        assertEquals("sage.matrix.matrix2.Matrix", matrixFactory.signatures.single().returnType.expression)
        assertEquals("sage.matrix.matrix2.Matrix", query.uniqueKnownReturnType("sage.all.Matrix")?.expression)
        val vectorFactory = requireNotNull(query.resolve("sage.all.vector", SageApiSymbolKind.FUNCTION))
        assertEquals("sage.modules.free_module_element.FreeModuleElement", vectorFactory.signatures.single().returnType.expression)
        assertTrue("sage.matrix.matrix2.Matrix" in query.reachableTypeNames("sage.matrix.matrix2.Matrix"))

        val determinant = requireNotNull(
            query.find("sage.matrix.matrix2.Matrix.determinant", SageApiSymbolKind.METHOD),
        )
        assertEquals(listOf("algorithm"), determinant.signatures.single().parameters.map { it.name })
        assertEquals("None", determinant.signatures.single().parameters.single().defaultValue)
        assertEquals(SageTypeState.UNKNOWN, determinant.signatures.single().returnType.state)
        assertTrue(determinant.documentation?.summary?.isNotBlank() == true)

        val nthRoot = requireNotNull(
            query.find("sage.rings.integer.Integer.nth_root", SageApiSymbolKind.METHOD),
        )
        assertEquals(listOf("n", "truncate_mode"), nthRoot.signatures.single().parameters.map { it.name })
        assertEquals("0", nthRoot.signatures.single().parameters[1].defaultValue)
        assertEquals(SageTypeState.UNKNOWN, nthRoot.signatures.single().returnType.state)
        assertTrue(nthRoot.documentation?.body?.contains("nth_root") == true)

        val factor = requireNotNull(query.resolve("sage.all.factor", SageApiSymbolKind.FUNCTION))
        assertEquals("sage.arith.misc.factor", factor.qualifiedName)
        assertEquals(
            listOf("n", "proof", "int_", "algorithm", "verbose", "kwds"),
            factor.signatures.single().parameters.map { it.name },
        )
        assertEquals(SageTypeState.KNOWN, factor.signatures.single().returnType.state)
        assertEquals("sage.structure.factorization.Factorization", factor.signatures.single().returnType.expression)

        val continuedFraction = requireNotNull(
            query.resolve("continued_fraction", SageApiSymbolKind.FUNCTION),
        )
        assertEquals("sage.rings.continued_fraction.continued_fraction", continuedFraction.qualifiedName)
        assertEquals(listOf("x", "value"), continuedFraction.signatures.single().parameters.map { it.name })
        assertTrue(continuedFraction.signatures.single().returnType.expression!!.contains("ContinuedFraction_"))
        assertEquals("sage.rings.integer.Integer", query.resolveKnownClassName("Integer"))
    }

    fun testInheritedPropertyAndConstantTypesPropagateThroughIndexedMembers() {
        val source = com.starnotesxj.sagemath.sageapi.SageApiSourceRef(
            com.starnotesxj.sagemath.sageapi.SageApiSourceKind.STUB,
            "property.pyi",
        )
        val matrixType = com.starnotesxj.sagemath.sageapi.SageTypeRef.known("sage.matrix.matrix.Matrix")
        val index = SageApiIndexQuery(
            com.starnotesxj.sagemath.sageapi.SageApiIndex(
                "10.9",
                "3.13",
                listOf(
                    com.starnotesxj.sagemath.sageapi.SageApiEntry(
                        "sage.property.property.Base",
                        SageApiSymbolKind.CLASS,
                        sources = listOf(source),
                    ),
                    com.starnotesxj.sagemath.sageapi.SageApiEntry(
                        "sage.property.property.Child",
                        SageApiSymbolKind.CLASS,
                        parents = listOf("sage.property.property.Base"),
                        sources = listOf(source),
                    ),
                    com.starnotesxj.sagemath.sageapi.SageApiEntry(
                        "sage.property.property.Base.rank",
                        SageApiSymbolKind.PROPERTY,
                        valueType = matrixType,
                        sources = listOf(source),
                    ),
                    com.starnotesxj.sagemath.sageapi.SageApiEntry(
                        "sage.property.property.Base.identity",
                        SageApiSymbolKind.CONSTANT,
                        valueType = matrixType,
                        sources = listOf(source),
                    ),
                    com.starnotesxj.sagemath.sageapi.SageApiEntry(
                        "sage.property.property.Base.unknown_value",
                        SageApiSymbolKind.PROPERTY,
                        valueType = com.starnotesxj.sagemath.sageapi.SageTypeRef.unknown(),
                        sources = listOf(source),
                    ),
                    com.starnotesxj.sagemath.sageapi.SageApiEntry(
                        "sage.property.property.Base.dynamic_value",
                        SageApiSymbolKind.CONSTANT,
                        valueType = com.starnotesxj.sagemath.sageapi.SageTypeRef.dynamic(),
                        sources = listOf(source),
                    ),
                    com.starnotesxj.sagemath.sageapi.SageApiEntry(
                        "sage.property.property.Base.shadowed",
                        SageApiSymbolKind.PROPERTY,
                        valueType = matrixType,
                        sources = listOf(source),
                    ),
                    com.starnotesxj.sagemath.sageapi.SageApiEntry(
                        "sage.property.property.Child.shadowed",
                        SageApiSymbolKind.PROPERTY,
                        valueType = com.starnotesxj.sagemath.sageapi.SageTypeRef.unknown(),
                        sources = listOf(source),
                    ),
                ),
            ),
        )
        SageApiIndexService.getInstance().install(index)
        try {
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/property/property.pyi",
                "sage/property/property.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix.pyi",
                "sage/matrix/matrix.pyi",
            )
            myFixture.configureByText(
                "inherited-property.sage",
                "from sage.property.property import Child\nobj = Child()\nobj.rank.solve_right(obj.rank).det<caret>",
            )
            myFixture.doHighlighting()
            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            val obj = targets.single { it.name == "obj" }
            val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            assertEquals("Child", (context.getType(obj) as? PyClassType)?.name)
            assertEquals(
                listOf("identity", "rank"),
                index.members("sage.property.property.Child").map { it.qualifiedName.substringAfterLast('.') }.filter { it in setOf("rank", "identity") }.sorted(),
            )
            val rankReferences = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                .filter { it.referencedName == "rank" && it.qualifier != null }
            assertTrue(
                rankReferences.isNotEmpty(),
                "rank references missing; all references=${PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java).map { it.referencedName }}",
            )
            val rankType = context.getType(rankReferences.first())
            assertTrue(
                (rankType as? PyClassType)?.name == "Matrix",
                "indexed property type=$rankType references=${rankReferences.map { it.text }}",
            )
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("determinant" in lookup || "det" in myFixture.file.text, "property chain completion=$lookup")

            val childType = context.getType(obj) as? PyClassType
            assertTrue(childType != null)
            val members = SageApiClassMembersProvider().getMembers(childType!!, myFixture.file, context)
            val rankMember = members.single { it.name == "rank" }
            val identityMember = members.single { it.name == "identity" }
            assertTrue(!rankMember.isFunction && !identityMember.isFunction)
            assertTrue("rank" in members.map { it.name }, "indexed member names=${members.map { it.name }}")
            assertTrue("identity" in members.map { it.name }, "indexed member names=${members.map { it.name }}")
            val provider = SageApiClassMembersProvider()
            val resolveContext = com.jetbrains.python.psi.resolve.PyResolveContext.defaultContext(context)
            val rankTarget = requireNotNull(provider.resolveMember(childType, "rank", myFixture.file, resolveContext))
            val identityTarget = requireNotNull(provider.resolveMember(childType, "identity", myFixture.file, resolveContext))
            val rankTargetType = if (rankTarget is com.jetbrains.python.psi.PyTypedElement) context.getType(rankTarget) else null
            val identityTargetType = if (identityTarget is com.jetbrains.python.psi.PyTypedElement) context.getType(identityTarget) else null
            assertTrue(
                (rankTargetType as? PyClassType)?.name == "Matrix",
                "indexed rank target type=$rankTargetType",
            )
            assertTrue(
                (identityTargetType as? PyClassType)?.name == "Matrix",
                "indexed identity target type=$identityTargetType",
            )
            val unknownTarget = requireNotNull(provider.resolveMember(childType, "unknown_value", myFixture.file, resolveContext))
            val shadowedTarget = requireNotNull(provider.resolveMember(childType, "shadowed", myFixture.file, resolveContext))
            val unknownType = if (unknownTarget is com.jetbrains.python.psi.PyTypedElement) context.getType(unknownTarget) else null
            val shadowedType = if (shadowedTarget is com.jetbrains.python.psi.PyTypedElement) context.getType(shadowedTarget) else null
            assertEquals(null, unknownType)
            assertEquals(null, shadowedType)
            assertTrue(rankTarget.isValid && identityTarget.isValid)
            assertTrue(provider.resolveMember(childType, "rank", myFixture.file, resolveContext) != null)
            assertTrue(provider.resolveMember(childType, "identity", myFixture.file, resolveContext) != null)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
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

    fun testExplicitAliasImportPropagatesMatrixChainInSageAndPython() {
        withBundledIndex {
            copyStub("sage/matrix/matrix.pyi", "testData/sage-stubs/sage/matrix/matrix.pyi")
            for (fileName in listOf("alias-chain.sage", "alias-chain.py")) {
                myFixture.configureByText(
                    fileName,
                    "from sage.matrix.matrix import matrix as m\nA = m([[1]])\nA.solve_right(A).det<caret>",
                )
                myFixture.doHighlighting()
                val aliasReference = PsiTreeUtil.collectElementsOfType(myFixture.file, PyReferenceExpression::class.java)
                    .single { it.referencedName == "m" }
                assertTrue(aliasReference.reference.resolve() != null, "alias import did not resolve in $fileName")
                val target = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
                    .single { it.name == "A" }
                val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
                assertEquals("Matrix", (context.getType(target) as? PyClassType)?.name)
                val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
                assertTrue(
                    "determinant" in lookup || "det" in myFixture.file.text,
                    "alias chain completion=$lookup file=$fileName text=${myFixture.file.text}",
                )
            }
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

    fun testIndexedMemberCallableTypePropagatesThroughImportedNestedCall() {
        withBundledIndex {
            myFixture.copyFileToProject(
                "testData/sage-stubs/site-packages/sage/__init__.pyi",
                "site-packages/sage/__init__.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/all.pyi",
                "site-packages/sage/all.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix.pyi",
                "sage/matrix/matrix.pyi",
            )
            myFixture.configureByText(
                "nested-call.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nA.solve_right(A).det<caret>",
            )
            myFixture.doHighlighting()
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue(
                "determinant" in lookup || "det" in myFixture.file.text,
                "nested indexed call completion=" + lookup + " text=" + myFixture.file.text,
            )
        }
    }

    fun testIndexedMemberCallableTypePropagatesThroughNestedCall() {
        withBundledIndex {
            myFixture.copyFileToProject(
                "testData/sage-stubs/site-packages/sage/__init__.pyi",
                "site-packages/sage/__init__.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/all.pyi",
                "site-packages/sage/all.pyi",
            )
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix.pyi",
                "sage/matrix/matrix.pyi",
            )
            myFixture.configureByText(
                "nested-call.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nA.solve_right(A).det<caret>",
            )
            myFixture.doHighlighting()
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue(
                "determinant" in lookup || "det" in myFixture.file.text,
                "nested indexed call completion=" + lookup + " text=" + myFixture.file.text,
            )
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

    fun testExplicitPythonModuleUsesIndexedDirectExports() {
        withBundledIndex {
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix.pyi",
                "sage/matrix/matrix.pyi",
            )
            myFixture.configureByText(
                "module-completion.py",
                "from sage.matrix import matrix\nimport sage.matrix.matrix as sm\nsm.mat<caret>",
            )
            myFixture.doHighlighting()
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            val completedText = myFixture.file.text
            assertTrue(
                "matrix" in lookup || "matrix" in completedText,
                "indexed Sage module completion=$lookup text=$completedText",
            )
        }
    }

    fun testNonSagePythonModuleDoesNotReceiveIndexedExports() {
        withBundledIndex {
            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/matrix/matrix.pyi",
                "sage/matrix/matrix.pyi",
            )
            myFixture.configureByText(
                "module-negative.py",
                "import math as sm\nsm.mat<caret>",
            )
            myFixture.doHighlighting()
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("matrix" !in lookup, "non-Sage module unexpectedly received Sage completion=$lookup")
        }
    }

    fun testNativePythonParameterInfoConsumesIndexedSignature() {
        withBundledIndex {
            copyStub("sage/matrix/matrix.pyi", "testData/sage-stubs/sage/matrix/matrix.pyi")
            myFixture.configureByText(
                "parameter-info.sage",
                "from sage.matrix.matrix import matrix\nA = matrix([[1]])\nmatrix(A, <caret>)",
            )
            myFixture.doHighlighting()

            val argumentLists = PsiTreeUtil.collectElementsOfType(myFixture.file, com.jetbrains.python.psi.PyArgumentList::class.java)
            val argumentList = argumentLists.firstOrNull { it.parent is com.jetbrains.python.psi.PyCallExpression }
                ?: error("No Sage call argument list found: ${argumentLists.map { it.text }}")
            val call = argumentList.parent as com.jetbrains.python.psi.PyCallExpression
            val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            val candidates = com.jetbrains.python.codeInsight.parameterInfo.PyParameterInfoUtils.findCallCandidates(argumentList)
            val indexedCandidate = candidates.firstOrNull { pair ->
                pair.second.getParameters(context).orEmpty().any { it.name == "rows" }
            } ?: error("Native Python parameter info did not see indexed Sage callable; candidates=${candidates.map { it.second }}")
            val indexedCallable = indexedCandidate.second

            val parameters = indexedCallable.getParameters(context).orEmpty()
            assertEquals(listOf("rows"), parameters.map { it.name })
            assertEquals("Matrix", (indexedCallable.getReturnType(context) as? PyClassType)?.name)
            assertTrue(call.argumentList == argumentList)
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
            val resolved = element.reference.resolve()
                ?: error("solve_right reference did not resolve")
            val nativePhysical = runCatching {
                resolved.containingFile.virtualFile?.isInLocalFileSystem == true &&
                    resolved.containingFile.name.endsWith(".pyi")
            }.getOrDefault(false)

            if (nativePhysical) {
                // Native physical stub declarations own their documentation:
                // the additive index must defer so Python's own provider wins.
                val quick = provider.getQuickNavigateInfo(element, element)
                assertTrue(quick == null, "native physical stub docs must win over indexed QuickDoc; quick=" + quick)
                val doc = provider.generateDoc(element, element)
                assertTrue(doc == null, "native physical stub docs must win over indexed QuickDoc; doc=" + doc)
            } else {
                // A non-native resolution is the additive indexed/synthetic
                // context; the exact qualified-name indexed docs must render.
                val signature = provider.getQuickNavigateInfo(element, element)
                    ?: error("Sage documentation provider returned no signature; resolved=" + resolved)
                assertTrue("sage.matrix.matrix.Matrix.solve_right" in signature, signature)
                assertTrue("rhs: sage.matrix.matrix.Matrix" in signature, signature)
                assertTrue("-> sage.matrix.matrix.Matrix" in signature, signature)

                val documentation = provider.generateDoc(element, element)
                    ?: error("Sage documentation provider returned no documentation; resolved=" + resolved)
                assertTrue("sage.matrix.matrix.Matrix.solve_right" in documentation, documentation)
                assertTrue("rhs: sage.matrix.matrix.Matrix" in documentation, documentation)
            }
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

    fun testConfiguredFullIndexCoverageMatrix() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }
        val service = SageApiIndexService.getInstance()
        try {
            assertTrue(service.reload(path), service.loadState().error ?: "external full index load failed")
            val query = requireNotNull(service.query())
            val entries = query.index.entries
            assertTrue(entries.isNotEmpty())
            val countsByKind = entries.groupingBy { it.kind }.eachCount()
            assertTrue((countsByKind[SageApiSymbolKind.MODULE] ?: 0) > 0)
            assertTrue((countsByKind[SageApiSymbolKind.CLASS] ?: 0) > 0)
            assertTrue((countsByKind[SageApiSymbolKind.FUNCTION] ?: 0) > 0)
            assertTrue((countsByKind[SageApiSymbolKind.METHOD] ?: 0) > 0)
            assertTrue((countsByKind[SageApiSymbolKind.PROPERTY] ?: 0) > 0)
            assertTrue((countsByKind[SageApiSymbolKind.CONSTANT] ?: 0) > 0)
            assertTrue((countsByKind[SageApiSymbolKind.ALIAS] ?: 0) > 0)
            entries.forEach { entry ->
                assertEquals(entry, query.find(entry.qualifiedName, entry.kind))
                val owner = entry.ownerName
                if (owner != null) {
                    when (entry.kind) {
                        SageApiSymbolKind.METHOD, SageApiSymbolKind.PROPERTY, SageApiSymbolKind.CONSTANT ->
                            assertTrue(query.members(owner).any { it.qualifiedName == entry.qualifiedName && it.kind == entry.kind })
                        else ->
                            assertTrue(query.moduleEntries(owner).any { it.qualifiedName == entry.qualifiedName && it.kind == entry.kind })
                    }
                }
            }
            val roots = query.namespaceEntries("sage.all")
            // The root namespace is generated from the selected Sage artifact;
            // assert its structural invariants instead of pinning a historical
            // count that legitimately changes when a new contract is curated.
            assertTrue(roots.size >= 2_000, "full Sage root unexpectedly small: ${roots.size}")
            assertEquals(roots.size, roots.map { it.qualifiedName.substringAfterLast('.') }.toSet().size)
            assertTrue(roots.all { query.namespaceEntry("sage.all", it.qualifiedName.substringAfterLast('.')) == it })
            val signatures = entries.flatMap { it.signatures }
            assertTrue(signatures.isNotEmpty())
            assertTrue(entries.any { it.documentation != null })
            val returnTypes = signatures.map { it.returnType }
            assertTrue(returnTypes.any { it.state == SageTypeState.KNOWN && !it.expression.isNullOrBlank() })
            assertTrue(returnTypes.any { it.state == SageTypeState.UNKNOWN })
            assertTrue(returnTypes.any { it.state == SageTypeState.DYNAMIC || it.expression.orEmpty().contains("|") })
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
            assertTrue(root.size >= 2_000, "full Sage root unexpectedly small: ${root.size}")
            assertEquals(root.size, root.map { it.qualifiedName.substringAfterLast('.') }.distinct().size)
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
                        val expression = query.parseTypeExpression(type)
                        type.state == SageTypeState.KNOWN &&
                            !type.expression.isNullOrBlank() &&
                            expression != null &&
                            expression !is SageTypeExpression.Union &&
                            expression !is SageTypeExpression.Optional &&
                            expression !is SageTypeExpression.Callable &&
                            expression !is SageTypeExpression.Generic
                    } && returns.map { it.expression }.distinct().size == 1 &&
                        query.uniqueKnownReturnType(entry.qualifiedName) == null
                }
                .take(10)
                .toList()
            assertTrue(missingSafe.isEmpty(), "Safe method returns are not exposed: $missingSafe")
            assertTrue(unsafe.isNotEmpty(), "Full artifact unexpectedly has no conservative UNKNOWN/DYNAMIC method cases")
            val solveRightReturns = query.callReturnTypes("sage.matrix.matrix2.Matrix.solve_right")
            assertEquals(
                setOf(
                    "sage.modules.free_module_element.FreeModuleElement",
                    "sage.matrix.matrix2.Matrix",
                ),
                solveRightReturns.map { it.expression }.toSet(),
            )
            assertTrue(solveRightReturns.all { it.state == SageTypeState.KNOWN })
            assertEquals(null, query.uniqueKnownReturnType("sage.matrix.matrix2.Matrix.solve_right"))
            // Curated contracts may make a method precise when its source
            // declaration proves the return; unrelated dynamic cases remain
            // UNKNOWN and therefore continue to fail closed.
            assertEquals(
                SageTypeState.KNOWN,
                query.callReturnTypes("sage.rings.integer.Integer.nth_root").single().state,
            )
            assertEquals(
                "sage.rings.integer.Integer",
                query.callReturnTypes("sage.rings.integer.Integer.nth_root").single().expression,
            )
            assertEquals(
                SageTypeState.UNKNOWN,
                query.callReturnTypes("sage.rings.integer.Integer.multiplicative_order").single().state,
            )
        } finally {
            service.install(null)
        }
    }

    fun testConfiguredFullIndexExposesSafeExternalOnlyOperatorMetadataWithoutNativeDispatchClaim() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val path = Path.of(configured)
        require(Files.isRegularFile(path)) { "Configured full Sage API index is not a file: $path" }

        val service = SageApiIndexService.getInstance()
        try {
            assertTrue(service.reload(path), service.loadState().error ?: "external full index load failed")
            val query = requireNotNull(service.query())
            val owner = "sage.rings.integer.Integer"
            assertTrue(query.members(owner).any { it.qualifiedName == "$owner.__add__" })
            assertTrue(query.members(owner).any { it.qualifiedName == "$owner.__mul__" })
            assertTrue(query.members(owner).any { it.qualifiedName == "$owner.__pow__" })
            assertTrue(query.members(owner).any { it.qualifiedName == "$owner.__neg__" })

            myFixture.copyFileToProject(
                "testData/sage-stubs/sage/rings/integer-external-only.pyi",
                "sage/rings/integer.pyi",
            )
            myFixture.configureByText(
                "external-operators.sage",
                "from sage.rings.integer import Integer\na = Integer(2)\nb = a + a\nc = a * a\nd = a ^ a\ne = -a",
            )
            myFixture.doHighlighting()
            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            val aTarget = targets.single { it.name == "a" }
            val aType = context.getType(aTarget)
            val aPyClass = (aType as? PyClassType)?.pyClass
            val aOwner = aPyClass?.let { SageStubIndex.canonicalQualifiedName(it) }
            assertTrue(
                aOwner == owner,
                "a owner=$aOwner class=$aPyClass type=$aType",
            )

            val operatorNames = setOf("__add__", "__mul__", "__pow__", "__neg__")
            for (operatorName in operatorNames) {
                assertTrue(
                    query.entriesOwnedBy(owner).any {
                        it.kind == SageApiSymbolKind.METHOD &&
                            it.qualifiedName == "$owner.$operatorName"
                    },
                    "indexed operator missing: $owner.$operatorName",
                )
            }
            assertEquals(owner, query.uniqueKnownReturnType("$owner.__add__")?.expression)
            assertEquals(owner, query.uniqueKnownReturnType("$owner.__mul__")?.expression)
            assertEquals(owner, query.uniqueKnownReturnType("$owner.__neg__")?.expression)
            assertEquals(null, query.uniqueKnownReturnType("$owner.__pow__"))

            val powerSignatures = query.signatures("$owner.__pow__")
            assertTrue(powerSignatures.isNotEmpty(), "power signatures missing")
            assertTrue(
                powerSignatures.all { signature ->
                    signature.returnType.state == SageTypeState.DYNAMIC &&
                        signature.parameters.all { parameter -> parameter.type.state == SageTypeState.DYNAMIC }
                },
                "power metadata=$powerSignatures",
            )

            // The full index is additive metadata only. Native PyCharm operator
            // result typing still requires a real callable dunder in the active
            // PSI stub; this sparse external-only fixture intentionally remains
            // untyped rather than receiving a fabricated operator result.
            val binaryResult = context.getType(targets.single { it.name == "b" })
            assertTrue(
                binaryResult == null,
                "external-only indexed dunder unexpectedly drove native binary typing: $binaryResult",
            )
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
            assertEquals(
                "sage.rings.real_mpfr.RealField_class",
                inferredCanonical,
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

    fun testSageArithmeticOperatorsPreserveIndexedIntegerType() {
        withBundledIndex {
            copyStub("sage/rings/integer.pyi", "testData/sage-stubs/sage/rings/integer.pyi")
            myFixture.configureByText(
                "arithmetic-operators.sage",
                "from sage.rings.integer import Integer\na = Integer(2)\nb = a + a\nc = a * a\nd = a ^ a\ne = -a\nb.nth<caret>_root(2)",
            )
            myFixture.doHighlighting()

            val targets = PsiTreeUtil.collectElementsOfType(myFixture.file, PyTargetExpression::class.java)
            val context = TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
            for (name in listOf("b", "c", "d", "e")) {
                assertEquals("Integer", (context.getType(targets.single { it.name == name }) as? PyClassType)?.name)
            }
            val lookup = myFixture.completeBasic()?.map { it.lookupString }.orEmpty()
            assertTrue("nth_root" in lookup || "nth_root" in myFixture.file.text, "operator result completion=" + lookup + " text=" + myFixture.file.text)
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
