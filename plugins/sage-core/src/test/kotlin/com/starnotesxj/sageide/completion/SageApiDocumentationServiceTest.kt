package com.starnotesxj.sageide.completion

import com.starnotesxj.sagemath.sageapi.SageApiDocumentation
import com.starnotesxj.sagemath.sageapi.SageApiDocumentationSidecar
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sageide.SagePluginTestBase
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.StandardCopyOption
import kotlin.test.assertEquals
import kotlin.test.assertNull

/**
 * Lazy documentation buckets: the python generator (sage-pycharm-stubgen
 * `sidecar.split_documentation`) writes `sage-api-docs/<xx>.ndjson` records,
 * this service reads them back from the external sidecar directory installed
 * next to the loaded index.  The bucket address is computed independently on
 * both sides (Java String.hashCode in Kotlin, an exact reimplementation in
 * Python) — the fixture is real python output, so a hash disagreement lands
 * it in the wrong bucket and the lookup misses.
 */
class SageApiDocumentationServiceTest : SagePluginTestBase() {
    private fun bucketEntry(documentation: SageApiDocumentation? = null): SageApiEntry = SageApiEntry(
        qualifiedName = "sage.demo.point.Point.xy",
        kind = SageApiSymbolKind.METHOD,
        documentation = documentation,
    )

    private fun copyPythonFixtureInto(docsRoot: Path): Path {
        val fixture = javaClass.classLoader.getResourceAsStream("sage-api-docs/python-bucket.ndjson")
            ?: error("python-generated bucket fixture is missing")
        val entry = bucketEntry()
        val bucketFile = docsRoot.resolve(
            SageApiDocumentationSidecar.resourceName(entry).substringAfterLast('/'),
        )
        Files.copy(fixture, bucketFile, StandardCopyOption.REPLACE_EXISTING)
        return bucketFile
    }

    fun testExternalPythonBucketServesDocumentation() {
        val docsRoot = Files.createTempDirectory("sage-api-docs")
        try {
            copyPythonFixtureInto(docsRoot)
            val service = SageApiDocumentationService { docsRoot }

            val loaded = service.documentation(bucketEntry())
                ?: error("document was not served from the python bucket")
            assertEquals("返回坐标二元组。", loaded.summary)
            assertEquals("返回 (x, y) 二元组。\n中文文档。", loaded.body)
            assertEquals(listOf("Point(1, 2).xy()"), loaded.examples)
        } finally {
            docsRoot.toFile().deleteRecursively()
        }
    }

    fun testInlineDocumentationWinsOverBucket() {
        val docsRoot = Files.createTempDirectory("sage-api-docs")
        try {
            copyPythonFixtureInto(docsRoot)
            val service = SageApiDocumentationService { docsRoot }
            val inline = SageApiDocumentation(summary = "内联优先。")

            assertEquals(inline, service.documentation(bucketEntry(inline)))
        } finally {
            docsRoot.toFile().deleteRecursively()
        }
    }

    fun testMissingBucketYieldsNull() {
        val docsRoot = Files.createTempDirectory("sage-api-docs")
        try {
            val service = SageApiDocumentationService { docsRoot }
            assertNull(service.documentation(bucketEntry()))
        } finally {
            docsRoot.toFile().deleteRecursively()
        }
    }
}
