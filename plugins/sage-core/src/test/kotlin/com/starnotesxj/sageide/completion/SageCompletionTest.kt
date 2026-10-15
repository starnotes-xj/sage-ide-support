package com.starnotesxj.sageide.completion

import com.intellij.openapi.command.WriteCommandAction
import com.intellij.codeInsight.completion.CompletionType
import com.intellij.openapi.extensions.ExtensionPointName
import com.intellij.openapi.fileTypes.PlainTextFileType
import com.intellij.psi.PsiDocumentManager
import com.intellij.ml.inline.completion.impl.lang.MLCompletionEditorLanguageResolver
import com.intellij.codeInsight.inline.completion.InlineCompletionProvider
import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageFileType
import com.starnotesxj.sageide.sugar.SageFullLineLanguageResolver
import com.starnotesxj.sageide.sugar.SageLanguage
import com.starnotesxj.sageide.type.SageIndexedTypeResolver
import com.starnotesxj.sageide.inline.SageInlineCandidate
import com.starnotesxj.sageide.inline.SageInlineCompletionProvider
import com.starnotesxj.sageide.inline.SageInlineNativeProtocol
import com.starnotesxj.sageide.inline.SageInlinePredictionService
import com.starnotesxj.sageide.inline.SageNativeInlineExecutable
import com.starnotesxj.sageide.inline.SageNativeInlineProcessScorer
import com.starnotesxj.sageide.inline.SageNativeInlineScoringBackend
import com.starnotesxj.sageide.inline.SageInlineScoringRequest
import com.starnotesxj.sageide.inline.SageInlineSemanticModel
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndex
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageTypeRef
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import java.nio.file.Files
import kotlin.time.Duration.Companion.milliseconds

class SageCompletionTest : SagePluginTestBase() {

    fun testFullLineCompatibilityResolvesOnlySageDialect() {
        assertSame(SageLanguage.INSTANCE, SageFullLineLanguageResolver.languageFor(SageFileType.INSTANCE))
        assertNull(SageFullLineLanguageResolver.languageFor(PlainTextFileType.INSTANCE))
    }

    fun testFullLineCompatibilityIsLoadedOnlyThroughItsOptionalExtension() {
        val resolvers = ExtensionPointName
            .create<MLCompletionEditorLanguageResolver>("com.intellij.ml.inline.completion.editorLanguageResolver")
            .extensionList
        assertTrue(
            "Sage Full Line resolver was not loaded from the optional descriptor fragment: $resolvers",
            resolvers.any { it is SageFullLineLanguageResolver },
        )
    }

    fun testSemanticInlineModelOnlyEmitsAUniqueTypedContinuation() {
        assertEquals(
            "g()",
            SageInlineSemanticModel.predict("lo", listOf(SageInlineCandidate("log", callable = true)))?.suffix,
        )
        assertNull(
            SageInlineSemanticModel.predict(
                "lo",
                listOf(
                    SageInlineCandidate("log", callable = true),
                    SageInlineCandidate("local_coordinates", callable = true),
                ),
            ),
        )
        assertEquals(
            "g()",
            SageInlineSemanticModel.predict(
                SageInlineScoringRequest(
                    prefix = "lo",
                    candidates = listOf(
                        SageInlineCandidate("log", callable = true),
                        SageInlineCandidate("local_coordinates", callable = true),
                    ),
                    memberContext = ".log\n.log\n",
                ),
            )?.suffix,
        )
    }

    fun testNativeInlineBoundaryRejectsUnknownCandidatesAndUsesSafeFallback() = runBlocking {
        val request = SageInlineScoringRequest(
            prefix = "lo",
            candidates = listOf(SageInlineCandidate("log", callable = true)),
        )
        val backend = SageNativeInlineScoringBackend(nativeScorer = { "not_a_member" })

        assertEquals("g()", backend.predict(request)?.suffix)
    }

    fun testNativeTimeoutUsesTheSameStrictContextualFallback() = runBlocking {
        val request = SageInlineScoringRequest(
            prefix = "lo",
            candidates = listOf(
                SageInlineCandidate("log", callable = true),
                SageInlineCandidate("local_coordinates", callable = true),
            ),
            memberContext = ".log\n.log\n",
        )
        val backend = SageNativeInlineScoringBackend(
            nativeScorer = {
                delay(30)
                "log"
            },
            deadline = 1.milliseconds,
        )

        assertEquals("g()", backend.predict(request)?.suffix)
    }

    fun testInlinePreparationFindsAConcreteReceiverAndCodeOnlyContext() {
        val curve = "sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field"
        val point = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field"
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(
                SageApiIndex(
                    "10.9",
                    "3.13",
                    listOf(
                        SageApiEntry(curve, SageApiSymbolKind.CLASS),
                        SageApiEntry(point, SageApiSymbolKind.CLASS),
                        SageApiEntry(
                            "sage.all.EllipticCurve",
                            SageApiSymbolKind.FUNCTION,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(curve))),
                        ),
                        SageApiEntry(
                            "$curve.random_point",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(point))),
                        ),
                        SageApiEntry("$point.log", SageApiSymbolKind.METHOD),
                        SageApiEntry("$point.local_coordinates", SageApiSymbolKind.METHOD),
                    ),
                ),
            ),
        )
        try {
            myFixture.configureByText(
                "inline-point.sage",
                "P = EllipticCurve().random_point()\n" +
                    "P.log(P)\n" +
                    "# .local_coordinates in a comment is not predictor context\n" +
                    "P.log(P)\n" +
                    "P.lo<caret>",
            )
            PsiDocumentManager.getInstance(myFixture.project).commitAllDocuments()
            val request = SageInlinePredictionService.getInstance(myFixture.project)
                .prepareScoringRequest(myFixture.file, myFixture.caretOffset)

            assertEquals("lo", request?.prefix)
            assertEquals(".random_point\n.log\n.log\n.lo", request?.memberContext)
            assertEquals("g()", request?.let(SageInlineSemanticModel::predict)?.suffix)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testNativeInlineWireProtocolFramesOnlyFilteredData() {
        val request = SageInlineScoringRequest(
            prefix = "lo",
            candidates = listOf(SageInlineCandidate("log", callable = true)),
            memberContext = ".log\n",
        )

        val wire = SageInlineNativeProtocol.encodeRequest(request)
        assertTrue(wire.startsWith("sage-inline-v1\t6c6f\t"))
        assertFalse("raw editor context leaked into native framing", wire.contains("CTF") || wire.contains("点"))
        assertEquals("log", SageInlineNativeProtocol.decodeResponse("sage-inline-v1\t6c6f67"))
        assertNull(SageInlineNativeProtocol.decodeResponse("unexpected\t6c6f67"))
    }

    fun testBundledNativeScorerRoundTripsWhenPresent() = runBlocking {
        val temporaryDirectory = Files.createTempDirectory("sage-inline-native-test")
        try {
            val executable = SageNativeInlineExecutable.extractTo(temporaryDirectory) ?: return@runBlocking
            val scorer = SageNativeInlineProcessScorer(executable)
            try {
                assertTrue("bundled native scorer did not start", scorer.warmUp())
                assertEquals(
                    "log",
                    scorer.chooseCandidate(
                        SageInlineScoringRequest(
                            prefix = "lo",
                            candidates = listOf(
                                SageInlineCandidate("log", callable = true),
                                SageInlineCandidate("local_coordinates", callable = true),
                            ),
                            memberContext = ".log\n.log\n",
                        ),
                    ),
                )
            } finally {
                scorer.close()
            }
        } finally {
            temporaryDirectory.toFile().deleteRecursively()
        }
    }

    fun testSageInlineProviderIsRegisteredThroughThePlatformExtensionPoint() {
        val providers = InlineCompletionProvider.extensions()
        assertTrue(
            "Sage semantic inline provider is absent from the platform extension point",
            providers.any { it is SageInlineCompletionProvider },
        )
        val directProviders = providers.filterNot {
            it.javaClass.name == "com.intellij.codeInsight.inline.completion.RemDevAggregatorInlineCompletionProvider"
        }
        assertTrue(
            "Sage must win direct-provider selection before Full Line: $directProviders",
            directProviders.firstOrNull() is SageInlineCompletionProvider,
        )
    }

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

    fun testConcreteIndexedQContractOverridesGenericPythonReceiverForCompletion() {
        val integer = "sage.rings.integer.Integer"
        val integerRing = "sage.rings.integer_ring.IntegerRing_class"
        val curve = "sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field"
        val point = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field"
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(
                SageApiIndex(
                    "10.9",
                    "3.13",
                    listOf(
                        SageApiEntry(integer, SageApiSymbolKind.CLASS),
                        SageApiEntry(integerRing, SageApiSymbolKind.CLASS),
                        SageApiEntry(curve, SageApiSymbolKind.CLASS),
                        SageApiEntry(point, SageApiSymbolKind.CLASS),
                        SageApiEntry(
                            "$integerRing.__call__",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(integer))),
                        ),
                        SageApiEntry(
                            "$curve.order",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(integer))),
                        ),
                        SageApiEntry(
                            "$curve.random_point",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(point))),
                        ),
                        SageApiEntry(
                            "$point.__rmul__",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(point))),
                        ),
                        SageApiEntry("$point.is_zero", SageApiSymbolKind.METHOD),
                        SageApiEntry("$point.order", SageApiSymbolKind.METHOD),
                        SageApiEntry(
                            "sage.all.EllipticCurve",
                            SageApiSymbolKind.FUNCTION,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(curve))),
                        ),
                        SageApiEntry(
                            "sage.all.ZZ",
                            SageApiSymbolKind.CONSTANT,
                            valueType = SageTypeRef.known(integerRing),
                        ),
                    ),
                ),
            ),
        )
        try {
            myFixture.configureByText(
                "q-contract.sage",
                "from sage.all import *\n\n" +
                    "bad_curve = EllipticCurve()\n" +
                    "curve_order = bad_curve.order()\n" +
                    "R = ZZ(2)\n" +
                    "Q = (curve_order // R) * bad_curve.random_point()\n" +
                    "Q.<caret>",
            )

            val lookup = myFixture.complete(CompletionType.BASIC, 0)?.map { it.lookupString }.orEmpty()
            assertTrue("static Q completion=$lookup", "is_zero" in lookup)
            assertTrue("static Q completion=$lookup", "order" in lookup)
            assertEquals("static Q completion must not duplicate the same member: $lookup", 1, lookup.count { it == "is_zero" })
            assertEquals("static Q completion must not duplicate the same member: $lookup", 1, lookup.count { it == "order" })

            myFixture.configureByText(
                "q-contract-smart.sage",
                "from sage.all import *\n\n" +
                    "bad_curve = EllipticCurve()\n" +
                    "curve_order = bad_curve.order()\n" +
                    "R = ZZ(2)\n" +
                    "Q = (curve_order // R) * bad_curve.random_point()\n" +
                    "Q.<caret>",
            )
            val smartLookup = myFixture.complete(CompletionType.SMART, 0)?.map { it.lookupString }.orEmpty()
            assertTrue("static Q smart completion=$smartLookup", "is_zero" in smartLookup)
            assertTrue("static Q smart completion=$smartLookup", "order" in smartLookup)
            assertEquals("static Q smart completion must not duplicate the same member: $smartLookup", 1, smartLookup.count { it == "is_zero" })
            assertEquals("static Q smart completion must not duplicate the same member: $smartLookup", 1, smartLookup.count { it == "order" })
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testConfiguredFullIndexCompletesTheUsersQBeforeRun() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val indexPath = java.nio.file.Path.of(configured)
        require(Files.isRegularFile(indexPath)) { "Configured full Sage API index is not a file: $indexPath" }
        val fullIndex = SageApiIndexQuery(SageApiIndexJsonReader.read(Files.readString(indexPath)))
        SageApiIndexService.getInstance().install(fullIndex)
        try {
            myFixture.configureByText(
                "test2.sage",
                "from sage.all import *\n\n" +
                    "bad_curve = EllipticCurve(GF(11), [1, 1])\n" +
                    "curve_order = bad_curve.order()\n" +
                    "R = ZZ(2)\n\n" +
                    "Q = (curve_order // R) * bad_curve.random_point()\n" +
                    "Q.<caret>",
            )
            val target = com.intellij.psi.util.PsiTreeUtil
                .collectElementsOfType(myFixture.file, com.jetbrains.python.psi.PyTargetExpression::class.java)
                .single { it.name == "Q" }
            val pointOwner = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field"
            assertEquals(
                "the complete index must retain Q's concrete reflected-scalar result",
                setOf(pointOwner),
                SageIndexedTypeResolver.ownersForTarget(target),
            )
            val lookup = myFixture.complete(CompletionType.BASIC, 0)?.map { it.lookupString }.orEmpty()
            assertTrue("full-index static Q completion=$lookup", "is_zero" in lookup)
            assertTrue("full-index static Q completion=$lookup", "order" in lookup)
            assertEquals("full-index static Q completion must not duplicate the same member: $lookup", 1, lookup.count { it == "is_zero" })
            assertEquals("full-index static Q completion must not duplicate the same member: $lookup", 1, lookup.count { it == "order" })

            myFixture.configureByText(
                "test2-smart.sage",
                "from sage.all import *\n\n" +
                    "bad_curve = EllipticCurve(GF(11), [1, 1])\n" +
                    "curve_order = bad_curve.order()\n" +
                    "R = ZZ(2)\n\n" +
                    "Q = (curve_order // R) * bad_curve.random_point()\n" +
                    "Q.<caret>",
            )
            val smartLookup = myFixture.complete(CompletionType.SMART, 0)?.map { it.lookupString }.orEmpty()
            assertTrue("full-index static Q smart completion=$smartLookup", "is_zero" in smartLookup)
            assertTrue("full-index static Q smart completion=$smartLookup", "order" in smartLookup)
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

    fun testExplicitSageAllImportGateCacheTracksPsiEdits() {
        myFixture.configureByText("explicit.sage", "value = 1\n")
        assertFalse(SageFileUtils.hasExplicitSageAllImport(myFixture.file))
        val document = checkNotNull(PsiDocumentManager.getInstance(myFixture.project).getDocument(myFixture.file))
        WriteCommandAction.runWriteCommandAction(myFixture.project) {
            document.insertString(0, "from sage.all import *\n")
            PsiDocumentManager.getInstance(myFixture.project).commitDocument(document)
        }
        assertTrue(SageFileUtils.hasExplicitSageAllImport(myFixture.file))
        WriteCommandAction.runWriteCommandAction(myFixture.project) {
            document.deleteString(0, "from sage.all import *\n".length)
            PsiDocumentManager.getInstance(myFixture.project).commitDocument(document)
        }
        assertFalse(SageFileUtils.hasExplicitSageAllImport(myFixture.file))
    }
}
