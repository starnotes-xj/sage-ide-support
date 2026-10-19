package com.starnotesxj.sageide.completion

import com.intellij.codeInsight.completion.CompletionType
import com.starnotesxj.sageide.SagePluginTestBase
import com.starnotesxj.sagemath.sageapi.SageApiIndexJsonReader
import com.starnotesxj.sagemath.sageapi.SageApiIndexQuery
import java.nio.file.Files
import java.nio.file.Path

/**
 * Reproduction of the user's WienerAttack loop from Downloads/test1.sage:
 * the for-loop variable must be inferred as Rational through the chain
 * `QQ(e) / QQ(N) -> continued_fraction() -> convergents() -> list[Rational]`
 * and offer numerator/denominator.  Runs against the REAL deployed index
 * (the slim schema-1 artifact documentation-sidecar produces) so a data or
 * engine regression is caught offline instead of being debugged through the
 * user's IDE.
 */
class SageFracChainCompletionTest : SagePluginTestBase() {

    private fun installFullIndex() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        val indexPath = Path.of(configured)
        require(Files.isRegularFile(indexPath)) {
            "Configured full Sage API index is not a file: $indexPath"
        }
        val index = SageApiIndexQuery(SageApiIndexJsonReader.read(Files.readString(indexPath)))
        SageApiIndexService.getInstance().install(index)
    }

    fun testLoopVariableFromConvergentsOffersRationalMembers() {
        val configured = System.getProperty("sage.external.fullIndex") ?: return
        installFullIndex()
        try {
            myFixture.configureByText(
                "frac-chain.sage",
                "from sage.all import *\n\n" +
                    "N = 0xb127\n" +
                    "e = 0x9d06\n" +
                    "d = None\n" +
                    "for frac in (QQ(e) / QQ(N)).continued_fraction().convergents():\n" +
                    "    frac.<caret>\n",
            )
            val lookup = myFixture.complete(CompletionType.BASIC, 0)?.map { it.lookupString }.orEmpty()
            assertTrue(
                "frac loop completion=$lookup must offer numerator",
                "numerator" in lookup,
            )
            assertTrue(
                "frac loop completion=$lookup must offer denominator",
                "denominator" in lookup,
            )
            assertEquals(
                "frac loop completion must not duplicate members: $lookup",
                1,
                lookup.count { it == "numerator" },
            )
        } finally {
            SageApiIndexService.getInstance().install(null)
        }
    }
}
