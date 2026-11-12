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
import com.starnotesxj.sagemath.sageapi.SageApiParameter
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

    fun testInheritedXyCompletesAtTwoLetterPrefix() {
        // The reported repro: xy is declared on EllipticCurvePoint_field; the
        // receiver's concrete class (EllipticCurvePoint_finite_field) has no
        // own xy.  Completion must still offer xy at the FULL two-letter
        // prefix (it does at the one-letter prefix).
        val integer = "sage.rings.integer.Integer"
        val curve = "sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic"
        val pointBase = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint"
        val pointField = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_field"
        val pointFF = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field"
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(
                SageApiIndex(
                    "10.9",
                    "3.13",
                    listOf(
                        SageApiEntry(integer, SageApiSymbolKind.CLASS),
                        SageApiEntry(curve, SageApiSymbolKind.CLASS),
                        SageApiEntry(pointBase, SageApiSymbolKind.CLASS, parents = listOf("sage.structure.element.AdditiveGroupElement")),
                        SageApiEntry(pointField, SageApiSymbolKind.CLASS, parents = listOf(pointBase)),
                        SageApiEntry(pointFF, SageApiSymbolKind.CLASS, parents = listOf(pointField)),
                        SageApiEntry(
                            "$curve.random_point",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(pointFF))),
                        ),
                        SageApiEntry(
                            "$pointBase.xy",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known("tuple[Any, ...]"))),
                        ),
                        SageApiEntry(
                            "$pointField.xy",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(pointField))),
                        ),
                        SageApiEntry(
                            "$pointFF.order",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(integer))),
                        ),
                        SageApiEntry(
                            "sage.all.EllipticCurve",
                            SageApiSymbolKind.FUNCTION,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(curve))),
                        ),
                    ),
                ),
            ),
        )
        try {
            val results = linkedMapOf<String, List<String>>()
            val elementResults = linkedMapOf<String, List<com.intellij.codeInsight.lookup.LookupElement>>()
            val texts = linkedMapOf<String, String>()
            for (prefix in listOf("", "x", "xy", "o", "or", "ord")) {
                myFixture.configureByText(
                    "repro-$prefix.sage",
                    "from sage.all import *\n" +
                        "E = EllipticCurve([1, 0])\n" +
                        "P = E.random_point()\n" +
                        "P.$prefix<caret>",
                )
                val caretElement = myFixture.file.findElementAt(myFixture.caretOffset)
                val ref = caretElement?.parent as? com.jetbrains.python.psi.PyReferenceExpression
                System.out.println(
                    "DIAG-REF prefix='$prefix' caretElement=" + (caretElement?.text ?: "null") +
                        " ref=" + (ref?.text ?: "null") +
                        " qualifier=" + (ref?.qualifier?.text ?: "null") +
                        " refType=" + (ref?.let {
                            val ctx = com.jetbrains.python.psi.types.TypeEvalContext.codeInsightFallback(myFixture.project)
                            ctx.getType(it)?.toString()
                        } ?: "null"),
                )
                val elements = myFixture.complete(CompletionType.BASIC, 0)?.toList().orEmpty()
                elementResults[prefix] = elements
                results[prefix] = elements.map { it.lookupString }
                texts[prefix] = myFixture.editor.document.text
            }
            System.out.println("DIAG-GRADIENT " + results.entries.joinToString(" | ") { "'" + it.key + "'->" + it.value + "}" })
            val indexedXy = elementResults.getValue("").filter { it.lookupString == "xy" }
            assertTrue("P. must contain the indexed xy candidate: $results", indexedXy.isNotEmpty())
            assertFalse(
                "platform control: an exact-match item without tail text is meaningless in an auto-popup",
                com.intellij.codeInsight.lookup.LookupElementBuilder.create("xy")
                    .withTypeText("sage.test.Owner")
                    .isWorthShowingInAutoPopup,
            )
            assertTrue(
                "xy must survive the platform's complete-prefix auto-popup check: $results",
                indexedXy.all { it.isWorthShowingInAutoPopup },
            )
            // The prefixed passes are the REAL gate: with a receiver whose
            // concrete class does not itself declare xy (inherited from
            // EllipticCurvePoint_field), every prefix pass must still offer
            // xy directly from the index — the delegation filter must not
            // hand inherited members to a native walk that drops them.
            // In the fixture a single matching item is AUTO-INSERTED instead
            // of showing a lookup (complete() then returns empty), and the
            // plugin's insert handler appends "()", so the document text is
            // the evidence the candidate was offered at that prefix.
            assertTrue("xy at '': " + results, "xy" in results.getValue(""))
            for (prefix in listOf("x", "xy")) {
                assertTrue("xy at '$prefix': " + texts, "P.xy(" in texts.getValue(prefix))
            }
            for (prefix in listOf("o", "or", "ord")) {
                assertTrue("order at '$prefix': " + texts, "P.order(" in texts.getValue(prefix))
            }
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testNativeAndIndexedXyAreDeduplicated() {
        val curve = "sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic"
        val pointField = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_field"
        val pointFF = "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field"
        SageApiIndexService.getInstance().install(
            SageApiIndexQuery(
                SageApiIndex(
                    "10.9",
                    "3.13",
                    listOf(
                        SageApiEntry(curve, SageApiSymbolKind.CLASS),
                        SageApiEntry(pointField, SageApiSymbolKind.CLASS),
                        SageApiEntry(pointFF, SageApiSymbolKind.CLASS, parents = listOf(pointField)),
                        SageApiEntry(
                            "$curve.random_point",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(pointFF))),
                        ),
                        SageApiEntry("$pointFF.order", SageApiSymbolKind.METHOD),
                        SageApiEntry(
                            "$pointField.xy",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(
                                SageApiSignature(parameters = listOf(SageApiParameter("self"))),
                            ),
                        ),
                        SageApiEntry(
                            "sage.all.EllipticCurve_generic",
                            SageApiSymbolKind.FUNCTION,
                            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known(curve))),
                        ),
                    ),
                ),
            ),
        )
        try {
            myFixture.addFileToProject("site-packages/sage/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/schemes/__init__.pyi", "")
            myFixture.addFileToProject("site-packages/sage/schemes/elliptic_curves/__init__.pyi", "")
            myFixture.addFileToProject(
                "site-packages/sage/schemes/elliptic_curves/ell_point.pyi",
                "class EllipticCurvePoint_field:\n" +
                    "    def xy(self) -> tuple[Any, ...]: ...\n\n" +
                    "class EllipticCurvePoint_finite_field(EllipticCurvePoint_field):\n" +
                    "    def order(self) -> int: ...\n",
            )
            myFixture.addFileToProject(
                "site-packages/sage/schemes/elliptic_curves/ell_generic.pyi",
                "from sage.schemes.elliptic_curves.ell_point import EllipticCurvePoint_finite_field\n\n" +
                    "class EllipticCurve_generic:\n" +
                    "    def random_point(self) -> EllipticCurvePoint_finite_field: ...\n",
            )
            myFixture.configureByText(
                "native-index-duplicate.sage",
                "from sage.schemes.elliptic_curves.ell_generic import EllipticCurve_generic\n" +
                    "E = EllipticCurve_generic()\n" +
                    "P = E.random_point()\n" +
                    "P.<caret>",
            )
            val receiver = com.intellij.psi.util.PsiTreeUtil
                .collectElementsOfType(myFixture.file, com.jetbrains.python.psi.PyReferenceExpression::class.java)
                .last { it.referencedName == "P" && it.qualifier == null }
            val receiverType = com.jetbrains.python.psi.types.TypeEvalContext.codeAnalysis(myFixture.project, myFixture.file)
                .getType(receiver)
            assertEquals(
                "native fixture must type P as a finite-field point: $receiverType",
                "EllipticCurvePoint_finite_field",
                (receiverType as? com.jetbrains.python.psi.types.PyClassType)?.pyClass?.name,
            )

            val elements = myFixture.complete(CompletionType.BASIC, 0)?.toList().orEmpty()
            assertTrue("both order and xy must remain available: ${elements.map { it.lookupString }}", "order" in elements.map { it.lookupString })
            assertEquals("native and indexed xy must be deduplicated: ${elements.map { it.lookupString }}", 1, elements.count { it.lookupString == "xy" })
            val xyPresentation = com.intellij.codeInsight.lookup.LookupElementPresentation()
            elements.single { it.lookupString == "xy" }.renderElement(xyPresentation)
            assertEquals("(self)", xyPresentation.tailFragments.joinToString("") { it.text })

            myFixture.configureByText(
                "native-index-duplicate-xy.sage",
                "from sage.schemes.elliptic_curves.ell_generic import EllipticCurve_generic\n" +
                    "E = EllipticCurve_generic()\n" +
                    "P = E.random_point()\n" +
                    "P.xy<caret>",
            )
            myFixture.complete(CompletionType.BASIC, 0)
            assertTrue("the unique P.xy candidate must be inserted: ${myFixture.editor.document.text}", "P.xy(" in myFixture.editor.document.text)
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }

    fun testForwardedSageMethodTailsAreGenericAndNonDuplicating() {
        val contributor = com.starnotesxj.sageide.sugar.SageBasicCompletionContributor()
        val methodTails = mapOf("xy" to "(self)", "order" to "(self, other)")

        fun completionResult(name: String, tail: String? = null): com.intellij.codeInsight.completion.CompletionResult {
            var builder = com.intellij.codeInsight.lookup.LookupElementBuilder.create(name)
                .withTypeText("sage.test.Owner")
            if (tail != null) builder = builder.withTailText(tail)
            return requireNotNull(
                com.intellij.codeInsight.completion.CompletionResult.wrap(
                    builder,
                    com.intellij.codeInsight.completion.PrefixMatcher.ALWAYS_TRUE,
                    com.intellij.codeInsight.completion.CompletionService.getCompletionService().emptySorter(),
                ),
            )
        }

        fun tailOf(result: com.intellij.codeInsight.completion.CompletionResult): String {
            val presentation = com.intellij.codeInsight.lookup.LookupElementPresentation()
            result.lookupElement.renderElement(presentation)
            return presentation.tailFragments.joinToString("") { it.text }
        }

        val xy = contributor.withIndexedSignatureTail(completionResult("xy"), methodTails)
        assertEquals("(self)", tailOf(xy))
        assertTrue(xy.lookupElement.isWorthShowingInAutoPopup)

        val order = contributor.withIndexedSignatureTail(completionResult("order"), methodTails)
        assertEquals("(self, other)", tailOf(order))

        val nativeXy = contributor.withIndexedSignatureTail(completionResult("xy", "(self)"), methodTails)
        assertEquals("(self)", tailOf(nativeXy))

        val unrelated = completionResult("unrelated")
        assertSame(unrelated, contributor.withIndexedSignatureTail(unrelated, methodTails))
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
                            "$point.xy",
                            SageApiSymbolKind.METHOD,
                            signatures = listOf(
                                SageApiSignature(parameters = listOf(SageApiParameter("self"))),
                            ),
                        ),
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

            val lookupElements = myFixture.complete(CompletionType.BASIC, 0)?.toList().orEmpty()
            val lookup = lookupElements.map { it.lookupString }
            assertTrue("static Q completion=$lookup", "is_zero" in lookup)
            assertTrue("static Q completion=$lookup", "order" in lookup)
            assertTrue("static Q completion=$lookup", "xy" in lookup)
            assertEquals("static Q completion must not duplicate the same member: $lookup", 1, lookup.count { it == "is_zero" })
            assertEquals("static Q completion must not duplicate the same member: $lookup", 1, lookup.count { it == "order" })
            val indexedXy = lookupElements.filter { it.lookupString == "xy" }
            assertEquals("static Q completion must not duplicate xy: $lookup", 1, indexedXy.size)
            val presentation = com.intellij.codeInsight.lookup.LookupElementPresentation()
            indexedXy.single().renderElement(presentation)
            assertEquals("(self)", presentation.tailFragments.joinToString("") { it.text })
            assertTrue(indexedXy.single().isWorthShowingInAutoPopup)

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

            myFixture.configureByText(
                "q-contract-xy.sage",
                "from sage.all import *\n\n" +
                    "bad_curve = EllipticCurve()\n" +
                    "curve_order = bad_curve.order()\n" +
                    "R = ZZ(2)\n" +
                    "Q = (curve_order // R) * bad_curve.random_point()\n" +
                    "Q.xy<caret>",
            )
            myFixture.complete(CompletionType.BASIC, 0)
            assertTrue("Q.xy must be offered and inserted: ${myFixture.editor.document.text}", "Q.xy(" in myFixture.editor.document.text)
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
