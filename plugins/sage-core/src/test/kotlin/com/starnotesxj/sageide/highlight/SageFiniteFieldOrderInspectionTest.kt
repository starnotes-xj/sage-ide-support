package com.starnotesxj.sageide.highlight

import com.starnotesxj.sageide.SagePluginTestBase

class SageFiniteFieldOrderInspectionTest : SagePluginTestBase() {

    fun testFlagsOnlyProvablyInvalidSmallLiteralOrders() {
        myFixture.configureByText(
            "fields.sage",
            """
                invalid = GF(<error descr="A finite field must have prime-power cardinality; '12' is not a valid field order.">12</error>)
                invalid_hex = FiniteField(<error descr="A finite field must have prime-power cardinality; '18' is not a valid field order.">0x12</error>)
                prime_field = GF(11)
                extension_field = GF(256)
                other_extension = GF(9)
                dynamic_order = GF(order)
                large_order = GF(1000000007)
            """.trimIndent(),
        )
        myFixture.enableInspections(SageFiniteFieldOrderInspection())

        myFixture.checkHighlighting()
    }

    fun testFlagsSignedZeroAndUnitOrdersButSkipsCompoundExpressions() {
        myFixture.configureByText(
            "signed-fields.sage",
            """
                negative = GF(<error descr="A finite field must have prime-power cardinality; '-12' is not a valid field order.">-12</error>)
                negative_hex = GF(<error descr="A finite field must have prime-power cardinality; '-18' is not a valid field order.">-0x12</error>)
                zero = GF(<error descr="A finite field must have prime-power cardinality; '0' is not a valid field order.">0</error>)
                one = GF(<error descr="A finite field must have prime-power cardinality; '1' is not a valid field order.">1</error>)
                positive = GF(+13)
                underscored = GF(<error descr="A finite field must have prime-power cardinality; '12' is not a valid field order.">1_2</error>)
                dynamic_identifier = GF(_12)
                nested_unary = GF(--12)
                computed = GF(-6 * 2)
            """.trimIndent(),
        )
        myFixture.enableInspections(SageFiniteFieldOrderInspection())

        myFixture.checkHighlighting()
    }
}
