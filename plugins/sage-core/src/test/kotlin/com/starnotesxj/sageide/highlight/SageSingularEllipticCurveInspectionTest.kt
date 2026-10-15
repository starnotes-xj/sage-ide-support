package com.starnotesxj.sageide.highlight

import com.starnotesxj.sageide.SagePluginTestBase

class SageSingularEllipticCurveInspectionTest : SagePluginTestBase() {

    fun testFlagsOnlyProvablySingularShortWeierstrassCurves() {
        myFixture.configureByText(
            "curves.sage",
            """
                singular_rational = EllipticCurve(<error descr="This Weierstrass model is singular for the specified base field.">[0, 0]</error>)
                singular_prime_field = EllipticCurve(GF(5), <error descr="This Weierstrass model is singular for the specified base field.">[2, 2]</error>)
                singular_extension = EllipticCurve(GF(25), <error descr="This Weierstrass model is singular for the specified base field.">[0, 0]</error>)
                nonsingular_rational = EllipticCurve([0, 1])
                nonsingular_prime_field = EllipticCurve(GF(5), [1, 1])
                singular_long_rational = EllipticCurve(<error descr="This Weierstrass model is singular for the specified base field.">[0, 0, 0, 0, 0]</error>)
                nonsingular_long_rational = EllipticCurve([0, 0, 1, -1, 0])
                singular_long_characteristic_two = EllipticCurve(GF(2), <error descr="This Weierstrass model is singular for the specified base field.">[0, 0, 0, -1, 0]</error>)
                singular_long_characteristic_three = EllipticCurve(GF(3), <error descr="This Weierstrass model is singular for the specified base field.">[0, 0, 0, 3, 1]</error>)
                explicit_rational_field = EllipticCurve(QQ, <error descr="This Weierstrass model is singular for the specified base field.">[0, 0, 0, 0, 0]</error>)
                dynamic_coefficients = EllipticCurve(GF(5), [a, b])
                dynamic_long_coefficients = EllipticCurve(GF(5), [a1, a2, a3, a4, a6])
                dynamic_field = EllipticCurve(F, [0, 0])
            """.trimIndent(),
        )
        myFixture.enableInspections(SageSingularEllipticCurveInspection())

        myFixture.checkHighlighting()
    }
}
