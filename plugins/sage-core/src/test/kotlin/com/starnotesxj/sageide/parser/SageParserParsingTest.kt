package com.starnotesxj.sageide.parser

import com.intellij.psi.PsiErrorElement
import com.intellij.psi.util.PsiTreeUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import com.jetbrains.python.psi.PyAssignmentStatement
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer

/**
 * End-to-end parse test for the real-world AES exercise file
 * (C:\Users\星记\Downloads\test.sage): the generator sugar statements must
 * parse as proper multi-target assignments with ZERO parser errors, and the
 * rest of the file must stay intact.
 */
class SageParserParsingTest : BasePlatformTestCase() {

    fun testSageSugarParsesWithoutParserErrors() {
        myFixture.configureByText("test.sage", AES_EXERCISE)

        val errors = PsiTreeUtil.collectElementsOfType(myFixture.file, PsiErrorElement::class.java)
        assertTrue("parser errors found: ${errors.joinToString { it.errorDescription }}", errors.isEmpty())
    }

    fun testSugarTargetsAreRealAssignmentTargets() {
        myFixture.configureByText("test.sage", AES_EXERCISE)

        val statements = PsiTreeUtil.collectElementsOfType(myFixture.file, PyAssignmentStatement::class.java)
        val sugarStatements = statements.filter { SageSugarAnalyzer.shapePredicate(it) }

        assertEquals(2, sugarStatements.size)

        val r = sugarStatements[0]
        assertEquals(listOf("R", "x"), r.targets.map { it.name })

        val f = sugarStatements[1]
        assertEquals(listOf("F", "a"), f.targets.map { it.name })
    }

    fun testPlainPythonPartsAreUntouched() {
        myFixture.configureByText("test.sage", AES_EXERCISE)

        val statements = PsiTreeUtil.collectElementsOfType(myFixture.file, PyAssignmentStatement::class.java)
        // e = F.from_integer(0x57) and the rest must remain ordinary assignments
        val plain = statements.filter { !SageSugarAnalyzer.shapePredicate(it) }
        assertTrue(plain.isNotEmpty())
        assertTrue(plain.any { it.targets.firstOrNull()?.name == "e" })
    }

    companion object {
        private val AES_EXERCISE = """
            # 必须指定 modulus=0x11B！Sage 默认用 Conway 多项式，结果和 AES 对不上
            R.<x> = GF(2)[]                                   # GF(2) 上多项式环
            F.<a> = GF(2^8, modulus=x^8 + x^4 + x^3 + x + 1)  # AES 的域

            # ── 整数 <-> 域元素 ──
            e = F.from_integer(0x57)            # 0x57 -> 元素 x^6+x^4+x^2+x+1
            print('e =', e, '| 整数表示:', e.to_integer(), '| 多项式:', e.polynomial())

            # ── 四则运算（+ 和 - 相同，都是异或）──
            b = F.from_integer(0x83)
            print('0x57 * 0x83 =', e * b, '| 等于 0xC1:', (e * b).to_integer() == 0xC1)
            print('a + b =', a + b, '| a - b =', a - b, '| a / b =', a / b)

            # ── 逆元 / 幂 / 阶 ──
            print('e 的逆元 =', e^(-1), '| e^254 =', e^254, '| 两者相等:', e^(-1) == e^254)
            print('x 的阶 =', a.multiplicative_order(), '(51 说明 0x11B 不可约但非本原)')

            # ── 本原元与离散对数 ──
            g = F.multiplicative_generator()
            print('本原元 g =', g, '| log_g(e) =', e.log(g), '| g^log_g(e) == e:', g^e.log(g) == e)

            # ── 域本身的信息 ──
            print('特征:', F.characteristic(), '| 元素个数:', F.order())
            print('modulus:', F.modulus())
            print('随机元素:', F.random_element())
        """.trimIndent()
    }
}
