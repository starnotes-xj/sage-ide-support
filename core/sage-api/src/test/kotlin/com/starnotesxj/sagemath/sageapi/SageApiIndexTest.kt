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
