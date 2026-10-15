package com.starnotesxj.sageide.highlight

import com.starnotesxj.sageide.SagePluginTestBase

class SageIncompatibleCrtInspectionTest : SagePluginTestBase() {

    fun testReportsOnlyProvablyIncompatibleLiteralCongruences() {
        myFixture.configureByText(
            "crt.sage",
            """
                impossible = <error descr="No CRT solution: residues 0 and 1 disagree modulo gcd(2, 4) = 2.">crt(0, 1, 2, 4)</error>
                impossible_negative_modulus = <error descr="No CRT solution: residues 0 and 1 disagree modulo gcd(-2, 4) = 2.">CRT(0, 1, -2, 4)</error>
                impossible_hex = <error descr="No CRT solution: residues 0 and 1 disagree modulo gcd(2, 4) = 2.">crt(0, 1, 0x2, 0x4)</error>
                compatible_non_coprime = crt(1, 3, 4, 6)
                compatible_coprime = crt(2, 1, 3, 5)
                dynamic_residue = crt(a, 1, 2, 4)
                dynamic_modulus = crt(0, 1, modulus, 4)
                zero_modulus = crt(0, 1, 0, 4)
                list_form = crt([2, 1], [3, 5])
                qualified_call = sage.arith.misc.crt(0, 1, 2, 4)
            """.trimIndent(),
        )
        myFixture.enableInspections(SageIncompatibleCrtInspection())

        myFixture.checkHighlighting()
    }
}
