package com.starnotesxj.sagemath.sageapi

/**
 * Structured, dependency-free representation of a known Sage/Python type
 * expression. The JSON index deliberately keeps the original expression;
 * this AST is derived lazily so existing artifacts remain compatible.
 */
sealed interface SageTypeExpression {
    data class Name(val qualifiedName: String) : SageTypeExpression

    /** A declared signature variable; produced only by contextual parsing. */
    data class TypeVariable(val name: String) : SageTypeExpression

    /** ParamSpec component access is represented explicitly and lowered fail-closed. */
    data class ParamSpecAccess(val name: String, val access: ParamSpecAccessKind) : SageTypeExpression

    data class Generic(
        val base: Name,
        val arguments: List<SageTypeExpression>,
    ) : SageTypeExpression
    data class Union(val members: List<SageTypeExpression>) : SageTypeExpression
    data class Optional(val element: SageTypeExpression) : SageTypeExpression
    data object NoneType : SageTypeExpression
    data object EllipsisType : SageTypeExpression
    data class Literal(val values: List<SageLiteralValue>) : SageTypeExpression
    data class Callable(
        /** null represents Callable[..., Return]. */
        val parameters: List<SageTypeExpression>?,
        val returnType: SageTypeExpression,
    ) : SageTypeExpression
}

sealed interface SageLiteralValue {
    data class StringValue(val value: String) : SageLiteralValue
    data class IntegerValue(val value: String) : SageLiteralValue
    data class BooleanValue(val value: Boolean) : SageLiteralValue
    data object NoneValue : SageLiteralValue
}

enum class ParamSpecAccessKind {
    ARGS,
    KWARGS,
}

/** Fail-closed parser for the type expression grammar emitted by Sage stubs. */
object SageTypeRefExpressionParser {
    fun parse(type: SageTypeRef): SageTypeExpression? =
        if (type.state == SageTypeState.KNOWN) type.expression?.let(::parse) else null

    fun parse(expression: String): SageTypeExpression? = parse(expression, emptySet())

    /** Parse an expression while recognizing only explicitly declared variables. */
    fun parse(
        expression: String,
        typeParameterNames: Set<String>,
        paramSpecNames: Set<String> = emptySet(),
    ): SageTypeExpression? = runCatching {
        val source = expression.trim()
        require(source.isNotEmpty())
        Parser(source, typeParameterNames, paramSpecNames).parseComplete()
    }.getOrNull()

    private class Parser(
        private val source: String,
        private val typeParameterNames: Set<String> = emptySet(),
        private val paramSpecNames: Set<String> = emptySet(),
    ) {
        private var position = 0

        fun parseComplete(): SageTypeExpression {
            val result = parseUnion()
            skipWhitespace()
            require(position == source.length)
            return result
        }

        private fun parseUnion(): SageTypeExpression {
            val members = mutableListOf(parsePrimary())
            while (consume('|')) members += parsePrimary()
            val flattened = members.flatMap {
                (it as? SageTypeExpression.Union)?.members ?: listOf(it)
            }.distinct()
            return if (flattened.size == 1) flattened.single() else SageTypeExpression.Union(flattened)
        }

        private fun parsePrimary(): SageTypeExpression {
            skipWhitespace()
            if (consume('(')) {
                val result = parseUnion()
                require(consume(')'))
                return result
            }
            if (consumeEllipsis()) return SageTypeExpression.EllipsisType
            val quote = peek()
            if (quote == '\'' || quote == '"') {
                val value = parseQuoted(quote)
                return runCatching { Parser(value, typeParameterNames, paramSpecNames).parseComplete() }
                    .getOrElse { SageTypeExpression.Literal(listOf(SageLiteralValue.StringValue(value))) }
            }
            if (consumeKeyword("None")) return SageTypeExpression.NoneType

            val name = parseQualifiedName()
            if (name.contains('.') && name.substringBeforeLast('.') in paramSpecNames) {
                val access = when (name.substringAfterLast('.')) {
                    "args" -> ParamSpecAccessKind.ARGS
                    "kwargs" -> ParamSpecAccessKind.KWARGS
                    else -> null
                }
                if (access != null) return SageTypeExpression.ParamSpecAccess(name.substringBeforeLast('.'), access)
            }
            skipWhitespace()
            if (!consume('[')) {
                return if (name in typeParameterNames || name in paramSpecNames) SageTypeExpression.TypeVariable(name)
                else SageTypeExpression.Name(name)
            }
            return when (name) {
                "Optional", "typing.Optional" -> {
                    val element = parseUnion()
                    require(consume(']'))
                    SageTypeExpression.Optional(element)
                }
                "Union", "typing.Union" -> {
                    val members = parseArguments()
                    require(members.size >= 2)
                    SageTypeExpression.Union(members.flatMap {
                        (it as? SageTypeExpression.Union)?.members ?: listOf(it)
                    }.distinct())
                }
                "Literal", "typing.Literal" -> parseLiteral()
                "Callable", "typing.Callable", "collections.abc.Callable" -> parseCallable()
                else -> SageTypeExpression.Generic(SageTypeExpression.Name(name), parseArguments())
            }
        }

        private fun parseArguments(): List<SageTypeExpression> {
            val arguments = mutableListOf<SageTypeExpression>()
            require(!consume(']'))
            do {
                arguments += parseUnion()
            } while (consume(','))
            require(consume(']'))
            return arguments
        }

        private fun parseLiteral(): SageTypeExpression.Literal {
            val values = mutableListOf<SageLiteralValue>()
            require(!consume(']'))
            do {
                values += parseLiteralValue()
            } while (consume(','))
            require(consume(']'))
            return SageTypeExpression.Literal(values)
        }

        private fun parseCallable(): SageTypeExpression.Callable {
            val parameters = if (consume('[')) {
                val values = mutableListOf<SageTypeExpression>()
                if (!consume(']')) {
                    do {
                        values += parseUnion()
                    } while (consume(','))
                    require(consume(']'))
                }
                values
            } else if (consumeEllipsis()) {
                null
            } else {
                listOf(parseUnion())
            }
            require(consume(','))
            val returnType = parseUnion()
            require(consume(']'))
            return SageTypeExpression.Callable(parameters, returnType)
        }

        private fun parseLiteralValue(): SageLiteralValue {
            skipWhitespace()
            val quote = peek()
            if (quote == '\'' || quote == '"') return SageLiteralValue.StringValue(parseQuoted(quote))
            if (consumeKeyword("True")) return SageLiteralValue.BooleanValue(true)
            if (consumeKeyword("False")) return SageLiteralValue.BooleanValue(false)
            if (consumeKeyword("None")) return SageLiteralValue.NoneValue
            val start = position
            consume('-')
            require(peek()?.isDigit() == true)
            while (peek()?.isDigit() == true) position++
            return SageLiteralValue.IntegerValue(source.substring(start, position))
        }

        private fun parseQualifiedName(): String {
            val segments = mutableListOf(parseIdentifier())
            while (true) {
                skipWhitespace()
                if (!consume('.')) break
                segments += parseIdentifier()
            }
            return segments.joinToString(".")
        }

        private fun parseIdentifier(): String {
            skipWhitespace()
            val start = position
            require(peek()?.let { it == '_' || it.isLetter() } == true)
            position++
            while (peek()?.let { it == '_' || it.isLetterOrDigit() } == true) position++
            return source.substring(start, position)
        }

        private fun parseQuoted(quote: Char): String {
            require(consume(quote))
            val result = StringBuilder()
            while (true) {
                val character = peek() ?: error("unterminated string")
                position++
                when (character) {
                    quote -> return result.toString()
                    '\\' -> {
                        val escaped = peek() ?: error("unterminated escape")
                        position++
                        result.append(
                            when (escaped) {
                                '\\' -> '\\'
                                '\'' -> '\''
                                '"' -> '"'
                                'n' -> '\n'
                                'r' -> '\r'
                                't' -> '\t'
                                else -> error("unsupported escape")
                            },
                        )
                    }
                    else -> result.append(character)
                }
            }
        }

        private fun consumeEllipsis(): Boolean {
            skipWhitespace()
            if (!source.startsWith("...", position)) return false
            position += 3
            return true
        }

        private fun consumeKeyword(keyword: String): Boolean {
            skipWhitespace()
            if (!source.startsWith(keyword, position)) return false
            val end = position + keyword.length
            if (end < source.length && (source[end] == '_' || source[end].isLetterOrDigit())) return false
            position = end
            return true
        }

        private fun consume(character: Char): Boolean {
            skipWhitespace()
            if (peek() != character) return false
            position++
            return true
        }

        private fun peek(): Char? = source.getOrNull(position)

        private fun skipWhitespace() {
            while (peek()?.isWhitespace() == true) position++
        }
    }
}
