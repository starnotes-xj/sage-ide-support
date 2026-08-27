package com.starnotesxj.sagemath.sageapi

/** Dependency-free reader for the stable JSON emitted by SageApiIndexJsonWriter. */
object SageApiIndexJsonReader {
    fun read(json: String): SageApiIndex {
        val root = JsonParser(json).parse().asObject("$")
        val schemaVersion = root.requiredInteger("schemaVersion")
        require(schemaVersion == SAGE_API_SCHEMA_VERSION) {
            "Unsupported Sage API schema version: " + schemaVersion
        }
        val sourceDigests = root.optionalObject("sourceDigests")
            ?.mapValues { (_, value) -> value.asString("$.sourceDigests") }
            ?: emptyMap()
        return SageApiIndex(
            sageVersion = root.requiredString("sageVersion"),
            pythonVersion = root.requiredString("pythonVersion"),
            generatorVersion = root.optionalString("generatorVersion") ?: "sage-api-index/unknown",
            sourceDigests = sourceDigests,
            entries = root.requiredArray("entries").mapIndexed { index, value -> parseEntry(value, "$.entries[" + index + "]") },
            schemaVersion = schemaVersion,
        )
    }

    private fun parseEntry(value: Any?, path: String): SageApiEntry {
        val objectValue = value.asObject(path)
        return SageApiEntry(
            qualifiedName = objectValue.requiredString("qualifiedName", path),
            kind = objectValue.requiredEnum("kind", path),
            signatures = objectValue.optionalArray("signatures")?.mapIndexed { index, item ->
                parseSignature(item, path + ".signatures[" + index + "]")
            } ?: emptyList(),
            valueType = objectValue.optionalValue("valueType")?.let { parseType(it, path + ".valueType") },
            parents = objectValue.optionalStringArray("parents", path),
            protocols = objectValue.optionalStringArray("protocols", path),
            aliases = objectValue.optionalStringArray("aliases", path),
            documentation = objectValue.optionalValue("documentation")?.let { parseDocumentation(it, path + ".documentation") },
            dynamicity = objectValue.optionalEnum("dynamicity", path) ?: SageApiDynamicity.UNKNOWN,
            confidence = objectValue.optionalEnum("confidence", path) ?: SageApiConfidence.UNKNOWN,
            sources = objectValue.optionalArray("sources")?.mapIndexed { index, item ->
                parseSource(item, path + ".sources[" + index + "]")
            } ?: emptyList(),
        )
    }

    private fun parseSource(value: Any?, path: String): SageApiSourceRef {
        val objectValue = value.asObject(path)
        return SageApiSourceRef(
            kind = objectValue.requiredEnum("kind", path),
            locator = objectValue.requiredString("locator", path),
            digest = objectValue.optionalString("digest"),
        )
    }

    private fun parseReturnEvidence(value: Any?, path: String): SageApiReturnEvidence {
        val objectValue = value.asObject(path)
        return SageApiReturnEvidence(
            kind = objectValue.requiredEnum("kind", path),
            returnType = parseType(objectValue.requiredValue("returnType", path), path + ".returnType"),
            source = parseSource(objectValue.requiredValue("source", path), path + ".source"),
        )
    }

    private fun parseSignature(value: Any?, path: String): SageApiSignature {
        val objectValue = value.asObject(path)
        return SageApiSignature(
            parameters = objectValue.optionalArray("parameters")?.mapIndexed { index, item ->
                parseParameter(item, path + ".parameters[" + index + "]")
            } ?: emptyList(),
            returnType = parseType(objectValue.requiredValue("returnType", path), path + ".returnType"),
            typeParameters = objectValue.optionalArray("typeParameters")?.mapIndexed { index, item ->
                parseTypeParameter(item, path + ".typeParameters[" + index + "]")
            } ?: emptyList(),
            trustedReturnEvidence = objectValue.optionalArray("trustedReturnEvidence")?.mapIndexed { index, item ->
                parseReturnEvidence(item, path + ".trustedReturnEvidence[" + index + "]")
            } ?: emptyList(),
        )
    }

    private fun parseTypeParameter(value: Any?, path: String): SageApiTypeParameter {
        val objectValue = value.asObject(path)
        return SageApiTypeParameter(
            name = objectValue.requiredString("name", path),
            kind = objectValue.optionalEnum<SageApiTypeParameterKind>("kind", path) ?: SageApiTypeParameterKind.TYPE_VARIABLE,
            bound = objectValue.optionalValue("bound")?.let { parseType(it, path + ".bound") },
            constraints = objectValue.optionalArray("constraints")?.mapIndexed { index, item ->
                parseType(item, path + ".constraints[" + index + "]")
            } ?: emptyList(),
        )
    }

    private fun parseParameter(value: Any?, path: String): SageApiParameter {
        val objectValue = value.asObject(path)
        return SageApiParameter(
            name = objectValue.requiredString("name", path),
            type = objectValue.optionalValue("type")?.let { parseType(it, path + ".type") } ?: SageTypeRef.unknown(),
            defaultValue = objectValue.optionalString("defaultValue"),
            optional = objectValue.optionalBoolean("optional") ?: (objectValue.optionalString("defaultValue") != null),
            keywordOnly = objectValue.optionalBoolean("keywordOnly") ?: false,
            variadic = objectValue.optionalBoolean("variadic") ?: false,
            positionalOnly = objectValue.optionalBoolean("positionalOnly") ?: false,
        )
    }

    private fun parseType(value: Any?, path: String): SageTypeRef {
        val objectValue = value.asObject(path)
        return SageTypeRef(
            expression = objectValue.optionalString("expression"),
            state = objectValue.requiredEnum("state", path),
        )
    }

    private fun parseDocumentation(value: Any?, path: String): SageApiDocumentation {
        val objectValue = value.asObject(path)
        return SageApiDocumentation(
            summary = objectValue.optionalString("summary"),
            body = objectValue.optionalString("body"),
            examples = objectValue.optionalStringArray("examples", path),
        )
    }

    private inline fun <reified T : Enum<T>> Map<String, Any?>.requiredEnum(name: String, path: String): T =
        optionalEnum<T>(name, path) ?: fail("Missing or invalid enum '" + name + "' at " + path)

    private inline fun <reified T : Enum<T>> Map<String, Any?>.optionalEnum(name: String, path: String): T? {
        val value = this[name] ?: return null
        val text = value.asString(path + "." + name)
        return try {
            enumValueOf<T>(text)
        } catch (_: IllegalArgumentException) {
            fail("Invalid enum '" + text + "' for '" + name + "' at " + path)
        }
    }

    private fun Map<String, Any?>.requiredString(name: String, path: String = "$"): String =
        (this[name] ?: fail("Missing '" + name + "' at " + path)).asString(path + "." + name)

    private fun Map<String, Any?>.optionalString(name: String): String? = this[name]?.asString(name)

    private fun Map<String, Any?>.requiredInteger(name: String): Int {
        val number = (this[name] ?: fail("Missing '" + name + "'")).asNumber(name)
        require(number.toDouble() == number.toInt().toDouble()) { "Expected integer at " + name }
        return number.toInt()
    }

    private fun Map<String, Any?>.optionalBoolean(name: String): Boolean? =
        if (!containsKey(name)) null else this[name] as? Boolean ?: fail("Expected boolean at " + name)

    private fun Map<String, Any?>.requiredValue(name: String, path: String): Any? =
        if (containsKey(name)) this[name] else fail("Missing '" + name + "' at " + path)

    private fun Map<String, Any?>.optionalValue(name: String): Any? = this[name]

    private fun Map<String, Any?>.requiredArray(name: String): List<Any?> =
        (this[name] ?: fail("Missing '" + name + "'")).asArray(name)

    private fun Map<String, Any?>.optionalArray(name: String): List<Any?>? = this[name]?.asArray(name)

    private fun Map<String, Any?>.optionalObject(name: String): Map<String, Any?>? = this[name]?.asObject(name)

    private fun Map<String, Any?>.optionalStringArray(name: String, path: String): List<String> =
        optionalArray(name)?.mapIndexed { index, value -> value.asString(path + "." + name + "[" + index + "]") } ?: emptyList()

    private fun Any?.asObject(path: String): Map<String, Any?> =
        this as? Map<String, Any?> ?: fail("Expected object at " + path)

    private fun Any?.asArray(path: String): List<Any?> =
        this as? List<Any?> ?: fail("Expected array at " + path)

    private fun Any?.asString(path: String): String =
        this as? String ?: fail("Expected string at " + path)

    private fun Any?.asNumber(path: String): Number =
        this as? Number ?: fail("Expected number at " + path)

    private fun fail(message: String): Nothing = throw IllegalArgumentException(message)

    private class JsonParser(private val source: String) {
        private var offset = 0

        fun parse(): Any? {
            skipWhitespace()
            val value = readValue()
            skipWhitespace()
            require(offset == source.length) { "Trailing JSON content at offset " + offset }
            return value
        }

        private fun readValue(): Any? {
            skipWhitespace()
            require(offset < source.length) { "Unexpected end of JSON" }
            return when (source[offset]) {
                '{' -> readObject()
                '[' -> readArray()
                '"' -> readString()
                't' -> readLiteral("true", true)
                'f' -> readLiteral("false", false)
                'n' -> readLiteral("null", null)
                '-', in '0'..'9' -> readNumber()
                else -> fail("Unexpected JSON character '" + source[offset] + "' at offset " + offset)
            }
        }

        private fun readObject(): Map<String, Any?> {
            expect('{')
            val result = linkedMapOf<String, Any?>()
            skipWhitespace()
            if (peek('}')) {
                offset++
                return result
            }
            while (true) {
                skipWhitespace()
                require(peek('"')) { "Expected object key at offset " + offset }
                val key = readString()
                require(!result.containsKey(key)) { "Duplicate JSON object key '" + key + "' at offset " + offset }
                skipWhitespace()
                expect(':')
                result[key] = readValue()
                skipWhitespace()
                if (peek('}')) {
                    offset++
                    return result
                }
                expect(',')
            }
        }

        private fun readArray(): List<Any?> {
            expect('[')
            val result = mutableListOf<Any?>()
            skipWhitespace()
            if (peek(']')) {
                offset++
                return result
            }
            while (true) {
                result += readValue()
                skipWhitespace()
                if (peek(']')) {
                    offset++
                    return result
                }
                expect(',')
            }
        }

        private fun readString(): String {
            expect('\"')
            return buildString {
                while (offset < source.length) {
                    when (val character = source[offset++]) {
                        '\"' -> return@buildString
                        '\\' -> {
                            require(offset < source.length) { "Incomplete escape at offset " + offset }
                            when (val escaped = source[offset++]) {
                                '\"' -> append('\"')
                                '\\' -> append('\\')
                                '/' -> append('/')
                                'b' -> append('\b')
                                'f' -> append('\u000c')
                                'n' -> append('\n')
                                'r' -> append('\r')
                                't' -> append('\t')
                                'u' -> {
                                    require(offset + 4 <= source.length) { "Incomplete unicode escape at offset " + offset }
                                    val hex = source.substring(offset, offset + 4)
                                    require(hex.all { it in "0123456789abcdefABCDEF" }) { "Invalid unicode escape at offset " + offset }
                                    append(hex.toInt(16).toChar())
                                    offset += 4
                                }
                                else -> fail("Invalid escape '" + escaped + "' at offset " + offset)
                            }
                        }
                        else -> {
                            require(character.code >= 0x20) { "Control character in JSON string at offset " + offset }
                            append(character)
                        }
                    }
                }
                fail("Unterminated JSON string")
            }
        }

        private fun readNumber(): Number {
            val start = offset
            if (peek('-')) offset++
            require(offset < source.length) { "Incomplete number at offset " + offset }
            if (peek('0')) {
                offset++
            } else {
                require(source[offset] in '1'..'9') { "Invalid number at offset " + offset }
                while (offset < source.length && source[offset].isDigit()) offset++
            }
            var fractional = false
            if (peek('.')) {
                fractional = true
                offset++
                require(offset < source.length && source[offset].isDigit()) { "Invalid fraction at offset " + offset }
                while (offset < source.length && source[offset].isDigit()) offset++
            }
            if (offset < source.length && (source[offset] == 'e' || source[offset] == 'E')) {
                fractional = true
                offset++
                if (offset < source.length && (source[offset] == '+' || source[offset] == '-')) offset++
                require(offset < source.length && source[offset].isDigit()) { "Invalid exponent at offset " + offset }
                while (offset < source.length && source[offset].isDigit()) offset++
            }
            val text = source.substring(start, offset)
            return if (fractional) text.toDouble() else text.toLong()
        }

        private fun readLiteral(literal: String, value: Any?): Any? {
            require(source.regionMatches(offset, literal, 0, literal.length)) { "Expected '" + literal + "' at offset " + offset }
            offset += literal.length
            return value
        }

        private fun expect(character: Char) {
            require(offset < source.length && source[offset] == character) { "Expected '" + character + "' at offset " + offset }
            offset++
        }

        private fun peek(character: Char): Boolean = offset < source.length && source[offset] == character

        private fun skipWhitespace() {
            while (offset < source.length && source[offset].isWhitespace()) offset++
        }
    }
}
