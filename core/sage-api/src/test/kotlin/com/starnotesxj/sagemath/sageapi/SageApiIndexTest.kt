package com.starnotesxj.sagemath.sageapi

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFalse
import kotlin.test.assertNotNull
import kotlin.test.assertTrue

class SageApiIndexTest {
    @Test
    fun normalizerBuildsVersionedIndexFromRuntimeSources() {
        val result = SageApiNormalizer().normalize(
            SageApiVersion(sage = "10.6", python = "3.11"),
            listOf(
                SageRawSymbol(
                    qualifiedName = "sage.all.RingElement",
                    kind = SageApiSymbolKind.ALIAS,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi"),
                    aliases = listOf("sage.rings.ring.RingElement"),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.Integer",
                    kind = SageApiSymbolKind.CLASS,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi"),
                    parents = listOf("sage.rings.ring.RingElement"),
                    documentation = SageApiDocumentation(summary = "An integer in Sage."),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.Integer.nth_root",
                    kind = SageApiSymbolKind.METHOD,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi"),
                    signatures = listOf(
                        SageApiSignature(
                            parameters = listOf(
                                SageApiParameter("n", SageTypeRef.known("int")),
                                SageApiParameter("truncate", SageTypeRef.known("bool"), defaultValue = "False", optional = true),
                            ),
                            returnType = SageTypeRef.known("Integer"),
                        ),
                    ),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.factor",
                    kind = SageApiSymbolKind.FUNCTION,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi"),
                    signatures = listOf(
                        SageApiSignature(
                            parameters = listOf(
                                SageApiParameter("n", SageTypeRef.known("Integer")),
                                SageApiParameter("proof", SageTypeRef.known("bool"), defaultValue = "True", optional = true),
                            ),
                            returnType = SageTypeRef.known("list[tuple[Integer, Integer]]"),
                        ),
                        SageApiSignature(
                            parameters = listOf(
                                SageApiParameter("n", SageTypeRef.known("int")),
                                SageApiParameter("proof", SageTypeRef.known("bool"), defaultValue = "True", optional = true),
                            ),
                            returnType = SageTypeRef.known("list[tuple[Integer, Integer]]"),
                        ),
                    ),
                ),
            ),
        )
        val index = result.index

        assertEquals(1, index.schemaVersion)
        assertEquals("10.6", index.sageVersion)
        assertEquals("3.11", index.pythonVersion)
        assertTrue(result.diagnostics.isEmpty(), result.diagnostics.joinToString())

        val integer = index.entry("sage.all.Integer", SageApiSymbolKind.CLASS)
        assertNotNull(integer)
        assertEquals(listOf("sage.rings.ring.RingElement"), integer.parents)
        assertEquals("An integer in Sage.", integer.documentation?.summary)

        val nthRoot = index.entry("sage.all.Integer.nth_root", SageApiSymbolKind.METHOD)
        assertNotNull(nthRoot)
        assertEquals(listOf("n", "truncate"), nthRoot.signatures.single().parameters.map { it.name })
        assertEquals("Integer", nthRoot.signatures.single().returnType.expression)

        val factor = index.entry("sage.all.factor", SageApiSymbolKind.FUNCTION)
        assertNotNull(factor)
        assertEquals(2, factor.signatures.size)
        assertEquals("sage.rings.ring.RingElement", index.entry("sage.all.RingElement", SageApiSymbolKind.ALIAS)?.aliases?.single())
    }


    @Test
    fun extractorTracksPositionalOnlyKeywordOnlyAndVariadicParameters() {
        val extracted = SageStubExtractor().extract(
            SageStubSource(
                "sage.signature",
                "def f(a: int, /, b: int, *, c: str = 'x', **kwargs: object) -> str: ...",
                "signature.pyi",
            ),
        )
        val signature = extracted.single { it.qualifiedName == "sage.signature.f" }.signatures.single()
        assertEquals(listOf("a", "b", "c", "kwargs"), signature.parameters.map { it.name })
        assertTrue(signature.parameters[0].positionalOnly)
        assertFalse(signature.parameters[1].positionalOnly)
        assertTrue(signature.parameters[2].keywordOnly)
        assertTrue(signature.parameters[3].keywordOnly)
        assertTrue(signature.parameters[3].variadic)
        assertTrue(signature.parameters[2].optional)
    }

    @Test
    fun extractorPreservesExplicitTypeVarParamSpecSelfAndTypeMetadata() {
        val extracted = SageStubExtractor().extract(
            SageStubSource(
                "sage.generic",
                """
from typing import TypeVar
from typing_extensions import ParamSpec, Self
T = TypeVar("T", bound=int)
P = ParamSpec("P")
def identity(value: T) -> T: ...
def fluent(value: Self) -> Self: ...
""".trimIndent(),
                "generic.pyi",
            ),
        )
        val identity = extracted.single { it.qualifiedName == "sage.generic.identity" }.signatures.single()
        assertEquals(listOf(SageApiTypeParameter("T", bound = SageTypeRef.known("int"))), identity.typeParameters)
        assertEquals("T", identity.parameters.single().type.expression)
        assertEquals(SageTypeExpression.TypeVariable("T"), SageTypeRefExpressionParser.parse("T", setOf("T")))
        val fluent = extracted.single { it.qualifiedName == "sage.generic.fluent" }.signatures.single()
        assertEquals(listOf(SageApiTypeParameter("Self", SageApiTypeParameterKind.SELF)), fluent.typeParameters)
        assertEquals(SageTypeExpression.TypeVariable("Self"), SageTypeRefExpressionParser.parse("Self", setOf("Self")))
        val paramSpec = SageApiSignature(
            returnType = SageTypeRef.known("None"),
            typeParameters = listOf(SageApiTypeParameter("P", SageApiTypeParameterKind.PARAM_SPEC)),
        )
        val loaded = SageApiIndexJsonReader.read(
            SageApiIndexJsonWriter.write(SageApiIndex("10.9", "3.13", listOf(SageApiEntry("sage.generic.identity", SageApiSymbolKind.FUNCTION, signatures = listOf(identity)), SageApiEntry("sage.generic.fluent", SageApiSymbolKind.FUNCTION, signatures = listOf(fluent)), SageApiEntry("sage.generic.call", SageApiSymbolKind.FUNCTION, signatures = listOf(paramSpec)))))
        )
        assertEquals(listOf(SageApiTypeParameter("P", SageApiTypeParameterKind.PARAM_SPEC)), loaded.entry("sage.generic.call")?.signatures?.single()?.typeParameters)
    }

    @Test
    fun extractorScopesExplicitTypeParametersAndIgnoresDefaults() {
        val extracted = SageStubExtractor().extract(
            SageStubSource(
                "sage.generic",
                """
from typing import TypeVar
from typing_extensions import ParamSpec
from external import ImportedBound

T = TypeVar("T", str, bytes)
B = TypeVar("B", bound = ImportedBound)
P = typing_extensions.ParamSpec("P", default=[int])

class Container:
    Local = TypeVar("Local")

def outside(value: Local) -> Local: ...
def label(value: str = "T") -> int: ...
def self_label(value: str = "Self") -> int: ...
def constrained(value: T) -> T: ...
def bounded(value: B) -> B: ...
def parameterized(value: P) -> P: ...
""".trimIndent(),
                "generic-scope.pyi",
            ),
        ).associateBy { it.qualifiedName }

        assertTrue(extracted["sage.generic.outside"]?.signatures?.single()?.typeParameters.isNullOrEmpty())
        assertTrue(extracted["sage.generic.label"]?.signatures?.single()?.typeParameters.isNullOrEmpty())
        assertTrue(extracted["sage.generic.self_label"]?.signatures?.single()?.typeParameters.isNullOrEmpty())

        val constrained = extracted["sage.generic.constrained"]?.signatures?.single()
        assertEquals(
            listOf(SageTypeRef.known("str"), SageTypeRef.known("bytes")),
            constrained?.typeParameters?.single()?.constraints,
        )
        assertEquals(null, constrained?.typeParameters?.single()?.bound)

        val bounded = extracted["sage.generic.bounded"]?.signatures?.single()
        assertEquals(SageTypeRef.known("external.ImportedBound"), bounded?.typeParameters?.single()?.bound)
        assertTrue(bounded?.typeParameters?.single()?.constraints.orEmpty().isEmpty())

        val parameterized = extracted["sage.generic.parameterized"]?.signatures?.single()
        assertEquals(SageApiTypeParameterKind.PARAM_SPEC, parameterized?.typeParameters?.single()?.kind)
    }

    @Test
    fun extractorRecognizesImportedTypeVarAndParamSpecAliases() {
        val extracted = SageStubExtractor().extract(
            SageStubSource(
                "sage.aliases",
                """
from typing import TypeVar as TV
import typing as t
from typing_extensions import ParamSpec as PS
T = TV("T", bound=int)
P = PS("P")
Q = t.TypeVar("Q", str, bytes)
def identity(value: T) -> T: ...
def accepts(args: P.args, kwargs: P.kwargs) -> None: ...
def constrained(value: Q) -> Q: ...
""".trimIndent(),
                "aliases.pyi",
            ),
        ).associateBy { it.qualifiedName }

        assertEquals(SageTypeRef.known("int"), extracted["sage.aliases.identity"]?.signatures?.single()?.typeParameters?.single()?.bound)
        assertEquals(SageApiTypeParameterKind.PARAM_SPEC, extracted["sage.aliases.accepts"]?.signatures?.single()?.typeParameters?.single()?.kind)
        assertEquals(
            listOf(SageTypeRef.known("str"), SageTypeRef.known("bytes")),
            extracted["sage.aliases.constrained"]?.signatures?.single()?.typeParameters?.single()?.constraints,
        )
    }

    @Test
    fun extractorKeepsNestedClassScopeAndQuotedParameterSeparators() {
        val extracted = SageStubExtractor().extract(
            SageStubSource(
                "sage.nested",
                """
from typing import Literal

class Outer:
    class Inner:
        value: int
    def method(self) -> int: ...
    outer_value: int

def separated(value: Literal["a,b"], /, *, option: int) -> None: ...
""".trimIndent(),
                "nested.pyi",
            ),
        ).associateBy { it.qualifiedName }

        assertNotNull(extracted["sage.nested.Outer.Inner"])
        assertNotNull(extracted["sage.nested.Outer.Inner.value"])
        assertNotNull(extracted["sage.nested.Outer.method"])
        assertNotNull(extracted["sage.nested.Outer.outer_value"])
        assertEquals(null, extracted["sage.nested.method"])
        assertEquals(null, extracted["sage.nested.outer_value"])

        val signature = extracted["sage.nested.separated"]?.signatures?.single()
        assertEquals(listOf("value", "option"), signature?.parameters?.map { it.name })
        assertTrue(signature?.parameters?.single { it.name == "value" }?.positionalOnly == true)
        assertTrue(signature?.parameters?.single { it.name == "option" }?.keywordOnly == true)
    }

    @Test
    fun extractorParsesClassesMethodsPropertiesAliasesAndOverloads() {
        val extracted = SageStubExtractor().extract(
            SageStubSource("sage.all", FIXTURE, "all.pyi"),
        )
        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), extracted)

        assertEquals(listOf("sage.rings.ring.RingElement"), result.index.entry("sage.all.RingElement", SageApiSymbolKind.ALIAS)?.aliases)
        assertEquals(listOf("sage.rings.ring.RingElement"), result.index.entry("sage.all.Integer", SageApiSymbolKind.CLASS)?.parents)
        assertEquals(SageApiSymbolKind.PROPERTY, result.index.entry("sage.all.Integer.numerator", SageApiSymbolKind.PROPERTY)?.kind)
        assertEquals(2, result.index.entry("sage.all.factor", SageApiSymbolKind.FUNCTION)?.signatures?.size)
        assertEquals("all.pyi:4", result.index.entry("sage.all.Integer", SageApiSymbolKind.CLASS)?.sources?.single()?.locator)
    }

    @Test
    fun namespaceEntryScopesDirectExportsBeforeGlobalShortNameResolution() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/all.pyi")
        val other = SageApiSourceRef(SageApiSourceKind.STUB, "fixtures/sage/other.pyi")
        val index = SageApiIndex(
            sageVersion = "10.6",
            pythonVersion = "3.11",
            entries = listOf(
                SageApiEntry("sage.all.AffineSpace", SageApiSymbolKind.FUNCTION, sources = listOf(source)),
                SageApiEntry("sage.other.AffineSpace", SageApiSymbolKind.FUNCTION, sources = listOf(other)),
                SageApiEntry("sage.all.Duplicate", SageApiSymbolKind.FUNCTION, sources = listOf(source)),
                SageApiEntry("sage.all.Duplicate", SageApiSymbolKind.ALIAS, sources = listOf(source)),
            ),
        )
        val query = SageApiIndexQuery(index)

        assertEquals("sage.all.AffineSpace", query.namespaceEntry("sage.all", "AffineSpace")?.qualifiedName)
        assertEquals("sage.other.AffineSpace", query.namespaceEntry("sage.other", "AffineSpace")?.qualifiedName)
        assertEquals(null, query.resolve("AffineSpace"))
        assertEquals(null, query.namespaceEntry("sage.all", "Duplicate"))
    }

    @Test
    fun generatedArtifactRoundTripsThroughKotlinReaderAndKeepsAliases() {
        val artifact = SageApiIndexJsonReader.read(
            requireNotNull(javaClass.classLoader.getResourceAsStream("sage-api-index.json"))
                .bufferedReader().use { it.readText() },
        )
        val query = SageApiIndexQuery(artifact)
        assertEquals("10.6", artifact.sageVersion)
        assertEquals("3.11", artifact.pythonVersion)
        assertTrue(artifact.entries.size >= 40)
        assertEquals("sage.matrix.matrix.Matrix", query.resolveKnownClassName("sage.all.Matrix"))
        assertEquals("sage.matrix.matrix.Matrix", query.uniqueKnownReturnType("sage.all.matrix")?.expression)
        assertTrue(query.members("sage.matrix.matrix.Matrix").any { it.qualifiedName.endsWith("solve_right") })
        assertEquals("sage.matrix.matrix.Matrix", query.signatures("sage.matrix.matrix.Matrix.solve_right").single().returnType.expression)
        assertEquals(
            listOf("Integer", "Matrix", "matrix"),
            query.moduleEntries("sage.matrix.matrix").map { it.qualifiedName.substringAfterLast('.') },
        )
        assertEquals(
            query.moduleEntries("sage.matrix.matrix"),
            query.moduleEntries("sage.matrix.matrix"),
        )
    }

    @Test
    fun generatorProvidesOneSourceDrivenEntryPoint() {
        val generated = SageApiIndexGenerator().generate(
            SageApiVersion("10.6", "3.11"),
            listOf(SageStubSource("sage.all", FIXTURE, "all.pyi")),
        )
        assertNotNull(generated.index.entry("sage.all.factor", SageApiSymbolKind.FUNCTION))
        assertNotNull(generated.index.entry("sage.all.Integer", SageApiSymbolKind.CLASS))
        assertEquals("sage.rings.integer.Integer", generated.index.entry("sage.all.Integer.nth_root", SageApiSymbolKind.METHOD)?.signatures?.single()?.returnType?.expression)
    }

    @Test
    fun conflictingSameShapeSignaturesBecomeDynamicAndAreReported() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "fixture-a.pyi")
        val other = SageApiSourceRef(SageApiSourceKind.SIGNATURE, "fixture-b.json")
        val raw = listOf(
            SageRawSymbol(
                qualifiedName = "sage.all.factor",
                kind = SageApiSymbolKind.FUNCTION,
                source = source,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("n", SageTypeRef.known("int"))),
                        returnType = SageTypeRef.known("Integer"),
                    ),
                ),
            ),
            SageRawSymbol(
                qualifiedName = "sage.all.factor",
                kind = SageApiSymbolKind.FUNCTION,
                source = other,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("n", SageTypeRef.known("int"))),
                        returnType = SageTypeRef.known("Rational"),
                    ),
                ),
            ),
        )

        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), raw)
        val entry = result.index.entry("sage.all.factor", SageApiSymbolKind.FUNCTION)
        assertNotNull(entry)
        assertEquals(1, result.diagnostics.count { it.kind == SageApiDiagnosticKind.CONFLICT })
        assertEquals(SageTypeState.DYNAMIC, entry.signatures.single().returnType.state)
        assertEquals(SageApiDynamicity.DYNAMIC, entry.dynamicity)
    }

    @Test
    fun provablyDisjointKnownParameterSignaturesRemainOverloads() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "fixture-a.pyi")
        val other = SageApiSourceRef(SageApiSourceKind.SIGNATURE, "fixture-b.json")
        val raw = listOf(
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = source,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("value", SageTypeRef.known("str"))),
                        returnType = SageTypeRef.known("String"),
                    ),
                ),
            ),
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = other,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("value", SageTypeRef.known("bytes"))),
                        returnType = SageTypeRef.known("Bytes"),
                    ),
                ),
            ),
        )

        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), raw)
        val entry = result.index.entry("sage.all.parse", SageApiSymbolKind.FUNCTION)

        assertNotNull(entry)
        assertEquals(2, entry.signatures.size)
        assertEquals(setOf("String", "Bytes"), entry.signatures.mapNotNull { it.returnType.expression }.toSet())
        assertEquals(SageApiDynamicity.STATIC, entry.dynamicity)
        assertTrue(result.diagnostics.none { it.kind == SageApiDiagnosticKind.CONFLICT })
    }

    @Test
    fun unknownParameterTypeDoesNotJustifyDisjointOverloadRepresentation() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "fixture-a.pyi")
        val other = SageApiSourceRef(SageApiSourceKind.SIGNATURE, "fixture-b.json")
        val raw = listOf(
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = source,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("left")),
                        returnType = SageTypeRef.known("String"),
                    ),
                ),
            ),
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = other,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("right", SageTypeRef.known("bytes"))),
                        returnType = SageTypeRef.known("Bytes"),
                    ),
                ),
            ),
        )

        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), raw)
        val entry = result.index.entry("sage.all.parse", SageApiSymbolKind.FUNCTION)

        assertNotNull(entry)
        assertEquals(SageApiDynamicity.DYNAMIC, entry.dynamicity)
        assertEquals(SageTypeState.DYNAMIC, entry.signatures.single().returnType.state)
        assertEquals(1, result.diagnostics.count { it.kind == SageApiDiagnosticKind.CONFLICT })
    }

    @Test
    fun literalAndWideParameterTypesRemainDynamicBecauseTheyMayOverlap() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "fixture-a.pyi")
        val other = SageApiSourceRef(SageApiSourceKind.SIGNATURE, "fixture-b.json")
        val raw = listOf(
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = source,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("literal", SageTypeRef.known("Literal[0]"))),
                        returnType = SageTypeRef.known("Zero"),
                    ),
                ),
            ),
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = other,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("wide", SageTypeRef.known("int"))),
                        returnType = SageTypeRef.known("Integer"),
                    ),
                ),
            ),
        )

        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), raw)
        val entry = result.index.entry("sage.all.parse", SageApiSymbolKind.FUNCTION)

        assertNotNull(entry)
        assertEquals(SageApiDynamicity.DYNAMIC, entry.dynamicity)
        assertEquals(SageTypeState.DYNAMIC, entry.signatures.single().returnType.state)
        assertEquals(1, result.diagnostics.count { it.kind == SageApiDiagnosticKind.CONFLICT })
    }

    @Test
    fun differingArityRemainsDynamicBecauseCallShapeIsAmbiguous() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "fixture-a.pyi")
        val other = SageApiSourceRef(SageApiSourceKind.SIGNATURE, "fixture-b.json")
        val raw = listOf(
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = source,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("value", SageTypeRef.known("str"))),
                        returnType = SageTypeRef.known("String"),
                    ),
                ),
            ),
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = other,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(
                            SageApiParameter("value", SageTypeRef.known("bytes")),
                            SageApiParameter("encoding", SageTypeRef.known("str")),
                        ),
                        returnType = SageTypeRef.known("Bytes"),
                    ),
                ),
            ),
        )

        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), raw)
        val entry = result.index.entry("sage.all.parse", SageApiSymbolKind.FUNCTION)

        assertNotNull(entry)
        assertEquals(SageApiDynamicity.DYNAMIC, entry.dynamicity)
        assertEquals(SageTypeState.DYNAMIC, entry.signatures.single().returnType.state)
        assertEquals(1, result.diagnostics.count { it.kind == SageApiDiagnosticKind.CONFLICT })
    }

    @Test
    fun unknownReturnTypeDoesNotJustifyDisjointOverloadRepresentation() {
        val source = SageApiSourceRef(SageApiSourceKind.STUB, "fixture-a.pyi")
        val other = SageApiSourceRef(SageApiSourceKind.SIGNATURE, "fixture-b.json")
        val raw = listOf(
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = source,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("text", SageTypeRef.known("str"))),
                        returnType = SageTypeRef.unknown(),
                    ),
                ),
            ),
            SageRawSymbol(
                qualifiedName = "sage.all.parse", kind = SageApiSymbolKind.FUNCTION, source = other,
                signatures = listOf(
                    SageApiSignature(
                        parameters = listOf(SageApiParameter("binary", SageTypeRef.known("bytes"))),
                        returnType = SageTypeRef.known("Bytes"),
                    ),
                ),
            ),
        )

        val result = SageApiNormalizer().normalize(SageApiVersion("10.6", "3.11"), raw)
        val entry = result.index.entry("sage.all.parse", SageApiSymbolKind.FUNCTION)

        assertNotNull(entry)
        assertEquals(SageApiDynamicity.DYNAMIC, entry.dynamicity)
        assertEquals(SageTypeState.DYNAMIC, entry.signatures.single().returnType.state)
        assertEquals(1, result.diagnostics.count { it.kind == SageApiDiagnosticKind.CONFLICT })
    }

    @Test
    fun coverageReportSeparatesMissingNoSignatureDynamicAndConflicts() {
        val result = SageApiNormalizer().normalize(
            SageApiVersion("10.6", "3.11"),
            listOf(
                SageRawSymbol(
                    qualifiedName = "sage.all.Integer",
                    kind = SageApiSymbolKind.CLASS,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "all.pyi"),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.factor",
                    kind = SageApiSymbolKind.FUNCTION,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "all.pyi"),
                    dynamicity = SageApiDynamicity.DYNAMIC,
                    signatures = listOf(SageApiSignature.dynamic()),
                ),
            ),
        )
        val report = SageApiCoverage.analyze(
            result.index,
            expected = listOf(
                SageApiExpectedSymbol("sage.all.Integer", SageApiSymbolKind.CLASS),
                SageApiExpectedSymbol("sage.all.factor", SageApiSymbolKind.FUNCTION),
                SageApiExpectedSymbol("sage.all.GF", SageApiSymbolKind.FUNCTION),
            ),
            normalizationDiagnostics = result.diagnostics,
        )

        assertEquals(3, report.expectedCount)
        assertEquals(2, report.coveredCount)
        assertEquals(1, report.missing.size)
        assertEquals("sage.all.GF", report.missing.single().qualifiedName)
        assertEquals(listOf("sage.all.Integer"), report.withoutSignature.map { it.qualifiedName })
        assertEquals(listOf("sage.all.factor"), report.dynamic.map { it.qualifiedName })
        assertEquals(0.6667, report.coverageRatio, 0.0001)
        assertFalse(report.isComplete)
        assertTrue(report.render().contains("missing=1"))
    }

    @Test
    fun jsonWriterIsStableAndCarriesSchemaVersion() {
        val result = SageApiNormalizer().normalize(
            SageApiVersion("10.6", "3.11"),
            listOf(
                SageRawSymbol(
                    qualifiedName = "sage.all.ZZ",
                    kind = SageApiSymbolKind.CONSTANT,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "all.pyi"),
                    documentation = SageApiDocumentation(summary = "Integers"),
                ),
                SageRawSymbol(
                    qualifiedName = "sage.all.GF",
                    kind = SageApiSymbolKind.FUNCTION,
                    source = SageApiSourceRef(SageApiSourceKind.STUB, "all.pyi"),
                    signatures = listOf(SageApiSignature.dynamic()),
                ),
            ),
        )
        val json = SageApiIndexJsonWriter.write(result.index)

        assertTrue(json.startsWith("{\n  \"schemaVersion\": 1,"))
        assertTrue(json.indexOf("sage.all.GF") < json.indexOf("sage.all.ZZ"))
        assertTrue(json.contains("\"state\": \"DYNAMIC\""))
        assertTrue(json.contains("\"summary\": \"Integers\""))
    }

    @Test
    fun memberLookupUsesNearestDeclarationAcrossDiamondMro() {
        fun cls(name: String, parents: List<String> = emptyList()) = SageApiEntry(
            qualifiedName = name,
            kind = SageApiSymbolKind.CLASS,
            parents = parents,
        )
        fun method(owner: String, name: String) = SageApiEntry(
            qualifiedName = "$owner.$name",
            kind = SageApiSymbolKind.METHOD,
            signatures = listOf(SageApiSignature.dynamic()),
        )
        val index = SageApiIndex(
            "10.6",
            "3.11",
            listOf(
                cls("sage.O"),
                cls("sage.A", listOf("sage.O")),
                cls("sage.B", listOf("sage.O")),
                cls("sage.C", listOf("sage.A", "sage.B")),
                method("sage.O", "shared"),
                method("sage.A", "shared"),
                method("sage.B", "onlyB"),
            ),
        )
        val members = SageApiIndexQuery(index).members("sage.C")
        assertEquals(setOf("shared", "onlyB"), members.map { it.qualifiedName.substringAfterLast('.') }.toSet())
        assertEquals("sage.A.shared", members.single { it.qualifiedName.endsWith(".shared") }.qualifiedName)
    }

    @Test
    fun jsonReaderRoundTripsAndQueryFollowsParents() {
        val parent = SageApiEntry(
            qualifiedName = "sage.rings.RingElement",
            kind = SageApiSymbolKind.CLASS,
        )
        val child = SageApiEntry(
            qualifiedName = "sage.rings.Integer",
            kind = SageApiSymbolKind.CLASS,
            parents = listOf(parent.qualifiedName),
        )
        val method = SageApiEntry(
            qualifiedName = "sage.rings.RingElement.solve_right",
            kind = SageApiSymbolKind.METHOD,
            signatures = listOf(SageApiSignature.dynamic()),
        )
        val index = SageApiIndex("10.6", "3.11", listOf(method, child, parent))
        val loaded = SageApiIndexJsonReader.read(SageApiIndexJsonWriter.write(index))

        assertEquals(index.sageVersion, loaded.sageVersion)
        assertEquals(index.pythonVersion, loaded.pythonVersion)
        assertEquals(index.entries.toSet(), loaded.entries.toSet())
        assertTrue(SageApiIndexQuery(loaded).members("sage.rings.Integer").any { it.qualifiedName.endsWith("solve_right") })
    }

    @Test
    fun matrixFactoryAndGenericClassMembersAreQueryableWithoutMethodSpecialCases() {
        val matrix = SageApiEntry(
            qualifiedName = "sage.matrix.matrix",
            kind = SageApiSymbolKind.FUNCTION,
            signatures = listOf(SageApiSignature(returnType = SageTypeRef.known("sage.matrix.matrix.Matrix"))),
        )
        val matrixClass = SageApiEntry(
            qualifiedName = "sage.matrix.matrix.Matrix",
            kind = SageApiSymbolKind.CLASS,
            parents = listOf("sage.structure.SageObject"),
        )
        val solveRight = SageApiEntry(
            qualifiedName = "sage.matrix.matrix.Matrix.solve_right",
            kind = SageApiSymbolKind.METHOD,
        )
        val determinant = SageApiEntry(
            qualifiedName = "sage.matrix.matrix.Matrix.determinant",
            kind = SageApiSymbolKind.METHOD,
        )
        val index = SageApiIndex("10.6", "3.11", listOf(determinant, matrix, solveRight, matrixClass))
        val query = SageApiIndexQuery(index)

        assertEquals("sage.matrix.matrix.Matrix", query.callReturnTypes("sage.matrix.matrix").single().expression)
        assertEquals("sage.matrix.matrix.Matrix", query.uniqueKnownReturnType("sage.matrix.matrix")?.expression)
        assertEquals(setOf("solve_right", "determinant"), query.members("sage.matrix.matrix.Matrix").map { it.qualifiedName.substringAfterLast('.') }.toSet())
        assertEquals(SageApiSymbolKind.METHOD, query.members("sage.matrix.matrix.Matrix", "solve_right").single().kind)
    }

    @Test
    fun moduleEntriesUseIndexedOwnerMapAndKeepExportOrdering() {
        val module = SageApiEntry("sage.demo", SageApiSymbolKind.MODULE)
        val function = SageApiEntry("sage.demo.make", SageApiSymbolKind.FUNCTION)
        val klass = SageApiEntry("sage.demo.Matrix", SageApiSymbolKind.CLASS)
        val member = SageApiEntry("sage.demo.Matrix.solve", SageApiSymbolKind.METHOD)
        val query = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(member, klass, function, module)))

        assertEquals(listOf("Matrix", "make"), query.moduleEntries("sage.demo").map { it.qualifiedName.substringAfterLast('.') })
        assertEquals(listOf("Matrix", "make"), query.entriesOwnedBy("sage.demo").map { it.qualifiedName.substringAfterLast('.') })
        assertEquals(listOf("solve"), query.members("sage.demo.Matrix").map { it.qualifiedName.substringAfterLast('.') })
        assertEquals(query.moduleEntries("sage.demo"), query.moduleEntries("sage.demo"))
    }

    @Test
    fun uniqueKnownReturnTypeRejectsDynamicOrAmbiguousReturns() {
        val function = SageApiEntry(
            qualifiedName = "sage.all.factory",
            kind = SageApiSymbolKind.FUNCTION,
            signatures = listOf(
                SageApiSignature(returnType = SageTypeRef.known("sage.all.Integer")),
                SageApiSignature(returnType = SageTypeRef.known("sage.all.Rational")),
            ),
        )
        val ambiguous = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(function)))
        assertEquals(null, ambiguous.uniqueKnownReturnType("sage.all.factory"))
        assertEquals(null, ambiguous.uniqueKnownReturnType("missing"))

        val dynamic = function.copy(signatures = listOf(SageApiSignature.dynamic()))
        val dynamicQuery = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(dynamic)))
        assertEquals(null, dynamicQuery.uniqueKnownReturnType("sage.all.factory"))
    }

    @Test
    fun resolveKnownClassNameRequiresOneCanonicalClass() {
        val unique = SageApiEntry("sage.matrix.Matrix", SageApiSymbolKind.CLASS, aliases = listOf("Matrix"))
        val uniqueQuery = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(unique)))
        assertEquals("sage.matrix.Matrix", uniqueQuery.resolveKnownClassName("Matrix"))
        assertEquals("sage.matrix.Matrix", uniqueQuery.resolveKnownClassName("sage.matrix.Matrix[Integer]"))

        val left = SageApiEntry("sage.left.Matrix", SageApiSymbolKind.CLASS)
        val right = SageApiEntry("sage.right.Matrix", SageApiSymbolKind.CLASS)
        val ambiguous = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(left, right)))
        assertEquals(null, ambiguous.resolveKnownClassName("Matrix"))
    }

    @Test
    fun uniqueKnownReturnTypeRejectsMixedKnownAndUnknownOverloads() {
        val factory = SageApiEntry(
            qualifiedName = "sage.all.factory",
            kind = SageApiSymbolKind.FUNCTION,
            signatures = listOf(
                SageApiSignature(returnType = SageTypeRef.known("sage.all.Integer")),
                SageApiSignature(returnType = SageTypeRef.unknown()),
            ),
        )
        val query = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(factory)))
        assertEquals(null, query.uniqueKnownReturnType("sage.all.factory"))
    }

    @Test
    fun jsonReaderRejectsDuplicateQualifiedNameAndKind() {
        val duplicate = """
            {
              "schemaVersion": 1,
              "sageVersion": "10.6",
              "pythonVersion": "3.11",
              "entries": [
                {"qualifiedName":"sage.all.Integer","kind":"CLASS"},
                {"qualifiedName":"sage.all.Integer","kind":"CLASS"}
              ]
            }
        """.trimIndent()
        val error = runCatching { SageApiIndexJsonReader.read(duplicate) }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("duplicate qualified-name/kind"))
    }

    @Test
    fun jsonReaderRejectsKnownTypeWithoutExpression() {
        val invalid = """
            {
              "schemaVersion": 1,
              "sageVersion": "10.6",
              "pythonVersion": "3.11",
              "entries": [{
                "qualifiedName":"sage.all.factory",
                "kind":"FUNCTION",
                "signatures":[{
                  "returnType":{"state":"KNOWN","expression":null}
                }]
              }]
            }
        """.trimIndent()
        val error = runCatching { SageApiIndexJsonReader.read(invalid) }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("Known Sage type references require an expression"))
    }

    @Test
    fun jsonReaderRejectsFractionalSchemaVersionAndWrongBooleanType() {
        val fractional = """{"schemaVersion":1.5,"sageVersion":"10.6","pythonVersion":"3.11","entries":[]}"""
        val fractionalError = runCatching { SageApiIndexJsonReader.read(fractional) }.exceptionOrNull()
        assertNotNull(fractionalError)
        assertTrue(fractionalError.message.orEmpty().contains("Expected integer"))

        val wrongBoolean = """{
          "schemaVersion":1,
          "sageVersion":"10.6",
          "pythonVersion":"3.11",
          "entries":[{
            "qualifiedName":"sage.all.factory",
            "kind":"FUNCTION",
            "signatures":[{
              "parameters":[{"name":"x","optional":"yes"}],
              "returnType":{"state":"UNKNOWN","expression":null}
            }]
          }]
        }"""
        val booleanError = runCatching { SageApiIndexJsonReader.read(wrongBoolean) }.exceptionOrNull()
        assertNotNull(booleanError)
        assertTrue(booleanError.message.orEmpty().contains("Expected boolean"))
    }

    @Test
    fun memberLookupPrefersChildDeclarationOverParentDeclaration() {
        val parent = SageApiEntry("sage.Parent", SageApiSymbolKind.CLASS)
        val child = SageApiEntry("sage.Child", SageApiSymbolKind.CLASS, parents = listOf("sage.Parent"))
        val parentSolve = SageApiEntry("sage.Parent.solve", SageApiSymbolKind.METHOD)
        val childSolve = SageApiEntry("sage.Child.solve", SageApiSymbolKind.METHOD)
        val query = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(parentSolve, parent, child, childSolve)))
        val result = query.members("sage.Child", "solve")
        assertEquals(1, result.size)
        assertEquals("sage.Child.solve", result.single().qualifiedName)
    }

    @Test
    fun inheritedPropertyAndConstantLookupUsesC3OwnerPriority() {
        val parent = SageApiEntry("sage.Parent", SageApiSymbolKind.CLASS)
        val child = SageApiEntry(
            "sage.Child",
            SageApiSymbolKind.CLASS,
            parents = listOf("sage.Parent"),
        )
        val parentRank = SageApiEntry(
            "sage.Parent.rank",
            SageApiSymbolKind.PROPERTY,
            valueType = SageTypeRef.known("sage.matrix.Matrix"),
        )
        val parentIdentity = SageApiEntry(
            "sage.Parent.identity",
            SageApiSymbolKind.CONSTANT,
            valueType = SageTypeRef.known("sage.matrix.Matrix"),
        )
        val parentShadowed = SageApiEntry(
            "sage.Parent.shadowed",
            SageApiSymbolKind.PROPERTY,
            valueType = SageTypeRef.known("sage.matrix.Matrix"),
        )
        val childShadowed = SageApiEntry(
            "sage.Child.shadowed",
            SageApiSymbolKind.PROPERTY,
            valueType = SageTypeRef.unknown(),
        )
        val query = SageApiIndexQuery(
            SageApiIndex(
                "10.9",
                "3.13",
                listOf(parentRank, parentIdentity, parentShadowed, parent, child, childShadowed),
            ),
        )

        assertEquals("sage.Parent.rank", query.members("sage.Child", "rank").single().qualifiedName)
        assertEquals(SageApiSymbolKind.PROPERTY, query.members("sage.Child", "rank").single().kind)
        assertEquals("sage.Parent.identity", query.members("sage.Child", "identity").single().qualifiedName)
        assertEquals(SageApiSymbolKind.CONSTANT, query.members("sage.Child", "identity").single().kind)
        assertEquals("sage.Child.shadowed", query.members("sage.Child", "shadowed").single().qualifiedName)
        assertEquals(SageTypeRef.unknown(), query.members("sage.Child", "shadowed").single().valueType)
    }

    @Test
    fun jsonReaderRejectsDuplicateObjectKeys() {
        val duplicate = """{"schemaVersion":1,"schemaVersion":1,"sageVersion":"10.6","pythonVersion":"3.11","entries":[]}"""
        val error = runCatching { SageApiIndexJsonReader.read(duplicate) }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("Duplicate JSON object key"))
    }

    @Test
    fun trustedReturnEvidenceJsonRoundTripsAndConsensusHolds() {
        val manifestSource = SageApiSourceRef(
            SageApiSourceKind.SIGNATURE,
            "trusted/return-evidence.json",
            "ab".repeat(32),
        )
        val signature = SageApiSignature(
            trustedReturnEvidence = listOf(
                SageApiReturnEvidence(
                    SageApiReturnEvidenceKind.TRUSTED_MANIFEST,
                    SageTypeRef.known("sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic"),
                    manifestSource,
                ),
            ),
        )
        val method = SageApiEntry(
            "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint.curve",
            SageApiSymbolKind.METHOD,
            signatures = listOf(signature),
        )
        val index = SageApiIndex("10.9", "3.13", listOf(method))
        val loaded = SageApiIndexJsonReader.read(SageApiIndexJsonWriter.write(index))
        val loadedSignature = loaded.entry(
            "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint.curve",
            SageApiSymbolKind.METHOD,
        )!!.signatures.single()

        assertEquals(signature.trustedReturnEvidence, loadedSignature.trustedReturnEvidence)
        assertEquals(
            "sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic",
            SageApiIndexQuery(loaded).uniqueTrustedKnownReturnExpression(loadedSignature)?.expression,
        )
        assertEquals(SageTypeRef.unknown(), loadedSignature.returnType)
    }

    @Test
    fun uniqueTrustedKnownReturnExpressionRejectsEmptyOrNonKnownEvidence() {
        val emptySignature = SageApiSignature()
        val query = SageApiIndexQuery(SageApiIndex("10.9", "3.13", listOf(
            SageApiEntry("sage.a.f", SageApiSymbolKind.METHOD, signatures = listOf(emptySignature)),
        )))
        assertEquals(null, query.uniqueTrustedKnownReturnExpression(emptySignature))

        val unknownEvidence = runCatching {
            SageApiSignature(
                trustedReturnEvidence = listOf(
                    SageApiReturnEvidence(
                        SageApiReturnEvidenceKind.TRUSTED_MANIFEST,
                        SageTypeRef.unknown(),
                        SageApiSourceRef(SageApiSourceKind.SIGNATURE, "trusted/return-evidence.json", "cd".repeat(32)),
                    ),
                ),
            )
        }.exceptionOrNull()
        assertNotNull(unknownEvidence)
        assertTrue(unknownEvidence.message.orEmpty().contains("only KNOWN"))
    }

    @Test
    fun signatureModelRejectsConflictingOrDuplicatedTrustedEvidence() {
        val source = SageApiSourceRef(SageApiSourceKind.SIGNATURE, "trusted/return-evidence.json", "ef".repeat(32))
        val conflicting = runCatching {
            SageApiSignature(
                trustedReturnEvidence = listOf(
                    SageApiReturnEvidence(SageApiReturnEvidenceKind.TRUSTED_MANIFEST, SageTypeRef.known("sage.a.Left"), source),
                    SageApiReturnEvidence(SageApiReturnEvidenceKind.TRUSTED_MANIFEST, SageTypeRef.known("sage.a.Right"), source.copy(locator = "trusted/other.json")),
                ),
            )
        }.exceptionOrNull()
        assertNotNull(conflicting)
        assertTrue(conflicting.message.orEmpty().contains("must agree"))

        val wrongKind = runCatching {
            SageApiSignature(
                trustedReturnEvidence = listOf(
                    SageApiReturnEvidence(
                        SageApiReturnEvidenceKind.TRUSTED_MANIFEST,
                        SageTypeRef.known("sage.a.Left"),
                        SageApiSourceRef(SageApiSourceKind.STUB, "ell_point.pyi", "11".repeat(32)),
                    ),
                ),
            )
        }.exceptionOrNull()
        assertNotNull(wrongKind)
        assertTrue(wrongKind.message.orEmpty().contains("signature source"))
    }

    @Test
    fun jsonReaderRejectsMalformedTrustedEvidence() {
        val malformed = """
            {
              "schemaVersion": 1,
              "sageVersion": "10.9",
              "pythonVersion": "3.13",
              "entries": [{
                "qualifiedName": "sage.a.f",
                "kind": "METHOD",
                "signatures": [{
                  "returnType": {"state": "UNKNOWN", "expression": null},
                  "trustedReturnEvidence": [{
                    "kind": "TRUSTED_MANIFEST",
                    "returnType": {"state": "UNKNOWN", "expression": null},
                    "source": {"kind": "SIGNATURE", "locator": "trusted/return-evidence.json", "digest": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}
                  }]
                }]
              }]
            }
        """.trimIndent()
        val error = runCatching { SageApiIndexJsonReader.read(malformed) }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("only KNOWN"), error.message.orEmpty())
    }

    @Test
    fun loaderReadsResourceAndRejectsMalformedExternalPath() {
        val loader = SageApiIndexLoader()
        val resource = loader.fromResource(javaClass.classLoader, "fixtures/index-empty.json")
        assertNotNull(resource)
        assertEquals("10.6", resource.sageVersion)
        assertEquals(null, loader.fromPath(java.nio.file.Path.of("G:/missing/sage-api-index.json")))
        assertEquals("10.6", loader.externalOrBundled(java.nio.file.Path.of("G:/missing/sage-api-index.json"), javaClass.classLoader, "fixtures/index-empty.json")?.sageVersion)
    }

    @Test
    fun qualifiedUnknownTypeDoesNotFallbackToSimpleName() {
        val matrix = SageApiEntry("sage.matrix.Matrix", SageApiSymbolKind.CLASS)
        val query = SageApiIndexQuery(SageApiIndex("10.6", "3.11", listOf(matrix)))
        assertEquals(null, query.resolveKnownClassName("foreign.Matrix"))
        assertEquals("sage.matrix.Matrix", query.resolveKnownClassName("Matrix"))
    }

    @Test
    fun jsonReaderRejectsUnsupportedSchema() {
        val error = runCatching {
            SageApiIndexJsonReader.read("{\"schemaVersion\": 99, \"sageVersion\": \"10\", \"pythonVersion\": \"3\", \"entries\": []}")
        }.exceptionOrNull()
        assertNotNull(error)
        assertTrue(error.message.orEmpty().contains("Unsupported Sage API schema version"))
    }

    private companion object {
        val FIXTURE = """
            from sage.rings.ring import RingElement as RingElement
            from sage.rings.integer import Integer as Integer

            class Integer(RingElement):
                /* An integer in Sage. */
                def nth_root(self, n: int, truncate: bool = False) -> Integer: ...
                @property
                def numerator(self) -> Integer: ...

            @overload
            def factor(n: Integer, proof: bool = True) -> list[tuple[Integer, Integer]]: ...
            @overload
            def factor(n: int, proof: bool = True) -> list[tuple[Integer, Integer]]: ...

            pi: RealNumber
        """.trimIndent()
    }
}
