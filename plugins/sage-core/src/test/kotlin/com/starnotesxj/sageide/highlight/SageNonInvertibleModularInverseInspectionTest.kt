package com.starnotesxj.sageide.highlight

import com.starnotesxj.sageide.SagePluginTestBase

class SageNonInvertibleModularInverseInspectionTest : SagePluginTestBase() {

    fun testReportsOnlyLiteralIntegerCallsWithoutAnInverse() {
        myFixture.configureByText(
            "inverse-mod.sage",
            """
                invalid = <error descr="No modular inverse exists: gcd(6, 15) = 3, not 1.">inverse_mod(6, 15)</error>
                invalid_negative_modulus = <error descr="No modular inverse exists: gcd(6, -15) = 3, not 1.">inverse_mod(6, -15)</error>
                invalid_hex = <error descr="No modular inverse exists: gcd(18, 36) = 18, not 1.">inverse_mod(0x12, 0x24)</error>
                invalid_binary = <error descr="No modular inverse exists: gcd(6, 15) = 3, not 1.">inverse_mod(0b110, 0b1111)</error>
                invalid_underscored = <error descr="No modular inverse exists: gcd(1000, 10000) = 1000, not 1.">inverse_mod(1_000, 10_000)</error>
                valid = inverse_mod(5, 14)
                valid_unit_modulus = inverse_mod(7, 1)
                valid_negative_modulus = inverse_mod(3, -5)
                dynamic_value = inverse_mod(a, 15)
                dynamic_modulus = inverse_mod(6, modulus)
                zero_modulus = inverse_mod(6, 0)
                qualified_call = sage.arith.misc.inverse_mod(6, 15)
            """.trimIndent(),
        )
        myFixture.enableInspections(SageNonInvertibleModularInverseInspection())

        myFixture.checkHighlighting()
    }
}
