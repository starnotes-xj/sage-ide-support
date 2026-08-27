package com.starnotesxj.sagemath.sageapi

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertIs
import kotlin.test.assertNull

class SageTypeRefExpressionTest {
    @Test
    fun parsesNamesGenericsUnionsOptionalLiteralsAndCallables() {
        assertEquals(
            SageTypeExpression.Name("sage.matrix.matrix.Matrix"),
            SageTypeRefExpressionParser.parse("sage.matrix.matrix.Matrix"),
        )
        assertEquals(
            SageTypeExpression.Generic(
                SageTypeExpression.Name("list"),
                listOf(
                    SageTypeExpression.Generic(
                        SageTypeExpression.Name("tuple"),
                        listOf(
                            SageTypeExpression.Name("int"),
                            SageTypeExpression.Name("sage.rings.integer.Integer"),
                        ),
                    ),
                ),
            ),
            SageTypeRefExpressionParser.parse(" list [ tuple [ int, sage.rings.integer.Integer ] ] "),
        )
        assertEquals(
            SageTypeExpression.Union(
                listOf(SageTypeExpression.Name("int"), SageTypeExpression.NoneType),
            ),
            SageTypeRefExpressionParser.parse("int | None"),
        )
        assertEquals(
            SageTypeExpression.Optional(SageTypeExpression.Name("sage.matrix.matrix.Matrix")),
            SageTypeRefExpressionParser.parse("typing.Optional['sage.matrix.matrix.Matrix']"),
        )
        assertEquals(
            SageTypeExpression.Literal(
                listOf(
                    SageLiteralValue.IntegerValue("0"),
                    SageLiteralValue.IntegerValue("-1"),
                    SageLiteralValue.BooleanValue(true),
                    SageLiteralValue.BooleanValue(false),
                    SageLiteralValue.NoneValue,
                    SageLiteralValue.StringValue("matrix"),
                ),
            ),
            SageTypeRefExpressionParser.parse("Literal[0, -1, True, False, None, \"matrix\"]"),
        )
        assertEquals(
            SageTypeExpression.Callable(
                listOf(SageTypeExpression.Name("int"), SageTypeExpression.Generic(SageTypeExpression.Name("list"), listOf(SageTypeExpression.Name("str")))),
                SageTypeExpression.Name("sage.matrix.matrix.Matrix"),
            ),
            SageTypeRefExpressionParser.parse("Callable[[int, list[str]], sage.matrix.matrix.Matrix]"),
        )
    }

    @Test
    fun parsesForwardReferencesParenthesesAndEllipsisCallables() {
        assertEquals(
            SageTypeExpression.Generic(
                SageTypeExpression.Name("tuple"),
                listOf(SageTypeExpression.Name("int"), SageTypeExpression.EllipsisType),
            ),
            SageTypeRefExpressionParser.parse("(tuple[int, ...])"),
        )
        assertEquals(
            SageTypeExpression.Callable(null, SageTypeExpression.Name("typing.Any")),
            SageTypeRefExpressionParser.parse("collections.abc.Callable[..., typing.Any]"),
        )
        assertEquals(
            SageTypeExpression.Name("sage.matrix.matrix.Matrix"),
            SageTypeRefExpressionParser.parse("'sage.matrix.matrix.Matrix'"),
        )
    }

    @Test
    fun nonKnownStatesAndMalformedExpressionsFailClosed() {
        assertNull(SageTypeRefExpressionParser.parse(SageTypeRef.unknown()))
        assertNull(SageTypeRefExpressionParser.parse(SageTypeRef.dynamic()))

        listOf(
            "",
            " ",
            "list[",
            "list[]",
            "list[int",
            "list[int]]",
            "A || B",
            "A & B",
            "A, B",
            "A -> B",
            "Callable[[int],]",
            "Literal[]",
            "Literal[1.5]",
            "Literal[x]",
            "Literal['unterminated]",
        ).forEach { expression ->
            assertNull(SageTypeRefExpressionParser.parse(expression), expression)
        }
    }

    @Test
    fun recognizesOnlyExplicitlyDeclaredTypeVariables() {
        assertEquals(SageTypeExpression.TypeVariable("T"), SageTypeRefExpressionParser.parse("T", setOf("T")))
        assertEquals(SageTypeExpression.Name("T"), SageTypeRefExpressionParser.parse("T"))
        assertEquals(
            SageTypeExpression.Generic(SageTypeExpression.Name("list"), listOf(SageTypeExpression.TypeVariable("T"))),
            SageTypeRefExpressionParser.parse("list[T]", setOf("T")),
        )
    }

    @Test
    fun parsesParamSpecCallablesAndComponentsContextually() {
        val paramSpec = setOf("P")
        assertEquals(
            SageTypeExpression.Callable(
                listOf(SageTypeExpression.TypeVariable("P")),
                SageTypeExpression.Name("int"),
            ),
            SageTypeRefExpressionParser.parse("Callable[P, int]", emptySet(), paramSpec),
        )
        assertEquals(
            SageTypeExpression.ParamSpecAccess("P", ParamSpecAccessKind.ARGS),
            SageTypeRefExpressionParser.parse("P.args", emptySet(), paramSpec),
        )
        assertEquals(
            SageTypeExpression.ParamSpecAccess("P", ParamSpecAccessKind.KWARGS),
            SageTypeRefExpressionParser.parse("P.kwargs", emptySet(), paramSpec),
        )
        assertEquals(
            SageTypeExpression.Callable(
                listOf(
                    SageTypeExpression.Generic(
                        SageTypeExpression.Name("Concatenate"),
                        listOf(SageTypeExpression.TypeVariable("Self"), SageTypeExpression.TypeVariable("P")),
                    ),
                ),
                SageTypeExpression.TypeVariable("T"),
            ),
            SageTypeRefExpressionParser.parse(
                "Callable[Concatenate[Self, P], T]",
                setOf("T", "Self"),
                paramSpec,
            ),
        )
    }

    @Test
    fun parserKeepsStructuredNodesDistinct() {
        val expression = SageTypeRefExpressionParser.parse("dict[str, list[int] | None]")
        val generic = assertIs<SageTypeExpression.Generic>(expression)
        assertEquals("dict", generic.base.qualifiedName)
        val value = assertIs<SageTypeExpression.Union>(generic.arguments[1])
        assertEquals(2, value.members.size)
    }
}
