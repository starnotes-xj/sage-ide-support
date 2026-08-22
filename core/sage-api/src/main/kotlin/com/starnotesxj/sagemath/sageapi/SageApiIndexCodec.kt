package com.starnotesxj.sagemath.sageapi

/** Stable, dependency-free JSON writer for the versioned API index artifact. */
object SageApiIndexJsonWriter {
    fun write(index: SageApiIndex): String = buildString {
        appendLine("{")
        appendLine("  " + jsonField("schemaVersion", index.schemaVersion.toString()) + ",")
        appendLine("  " + jsonField("sageVersion", jsonString(index.sageVersion)) + ",")
        appendLine("  " + jsonField("pythonVersion", jsonString(index.pythonVersion)) + ",")
        appendLine("  " + jsonField("generatorVersion", jsonString(index.generatorVersion)) + ",")
        appendLine("  " + jsonField("sourceDigests", buildString {
            append("{")
            index.sourceDigests.entries.sortedBy { it.key }.forEachIndexed { offset, entry ->
                if (offset > 0) append(",")
                append(jsonField(entry.key, jsonString(entry.value)))
            }
            append("}")
        }) + ",")
        appendLine("  " + jsonField("entries", index.entries.sortedWith(compareBy<SageApiEntry> { it.qualifiedName }.thenBy { it.kind.name })
            .joinToString(prefix = "[", postfix = "]") { entryJson(it) }))
        appendLine("}")
    }

    private fun entryJson(entry: SageApiEntry): String {
        val fields = mutableListOf<String>()
        fields += jsonField("qualifiedName", jsonString(entry.qualifiedName))
        fields += jsonField("kind", jsonString(entry.kind.name))
        fields += jsonField("dynamicity", jsonString(entry.dynamicity.name))
        fields += jsonField("confidence", jsonString(entry.confidence.name))
        fields += jsonField("parents", stringArray(entry.parents))
        fields += jsonField("protocols", stringArray(entry.protocols))
        fields += jsonField("aliases", stringArray(entry.aliases))
        fields += jsonField("sources", entry.sources.joinToString(prefix = "[", postfix = "]") { source ->
            "{" + jsonField("kind", jsonString(source.kind.name)) + "," +
                jsonField("locator", jsonString(source.locator)) +
                (source.digest?.let { "," + jsonField("digest", jsonString(it)) } ?: "") + "}"
        })
        fields += jsonField("signatures", entry.signatures.joinToString(prefix = "[", postfix = "]", transform = ::signatureJson))
        entry.valueType?.let { fields += jsonField("valueType", typeJson(it)) }
        entry.documentation?.let { documentation ->
            fields += jsonField(
                "documentation",
                "{" +
                    jsonField("summary", documentation.summary?.let(::jsonString) ?: "null") + "," +
                    jsonField("body", documentation.body?.let(::jsonString) ?: "null") + "," +
                    jsonField("examples", stringArray(documentation.examples)) +
                    "}",
            )
        }
        return fields.joinToString(prefix = "{", postfix = "}", separator = ",")
    }

    private fun signatureJson(signature: SageApiSignature): String =
        "{" +
            jsonField("parameters", signature.parameters.joinToString(prefix = "[", postfix = "]", transform = ::parameterJson)) + "," +
            jsonField("returnType", typeJson(signature.returnType)) +
            "}"

    private fun parameterJson(parameter: SageApiParameter): String =
        "{" +
            jsonField("name", jsonString(parameter.name)) + "," +
            jsonField("type", typeJson(parameter.type)) + "," +
            jsonField("defaultValue", parameter.defaultValue?.let(::jsonString) ?: "null") + "," +
            jsonField("optional", parameter.optional.toString()) + "," +
            jsonField("keywordOnly", parameter.keywordOnly.toString()) + "," +
            jsonField("variadic", parameter.variadic.toString()) +
            "}"

    private fun typeJson(type: SageTypeRef): String =
        "{" +
            jsonField("state", jsonString(type.state.name)) + "," +
            jsonField("expression", type.expression?.let(::jsonString) ?: "null") +
            "}"

    private fun stringArray(values: List<String>): String = values.sorted().joinToString(prefix = "[", postfix = "]", transform = ::jsonString)

    private fun jsonField(name: String, value: String): String = jsonString(name) + ": " + value

    private fun jsonString(value: String): String = buildString {
        append('"')
        value.forEach { character ->
            when (character) {
                '\\' -> append("\\\\")
                '"' -> append("\\\"")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> if (character.code < 0x20) append("\\u%04x".format(character.code)) else append(character)
            }
        }
        append('"')
    }
}

object SageApiCoverage {
    fun analyze(
        index: SageApiIndex,
        expected: List<SageApiExpectedSymbol>,
        normalizationDiagnostics: List<SageApiDiagnostic> = emptyList(),
    ): SageApiCoverageReport {
        val orderedExpected = expected.distinct().sortedWith(compareBy<SageApiExpectedSymbol> { it.qualifiedName }.thenBy { it.kind.name })
        val covered = orderedExpected.filter { index.entry(it.qualifiedName, it.kind) != null }
        val missing = orderedExpected - covered.toSet()
        val withoutSignature = covered.filter { expectedSymbol ->
            index.entry(expectedSymbol.qualifiedName, expectedSymbol.kind)?.signatures.isNullOrEmpty() &&
                expectedSymbol.kind in setOf(SageApiSymbolKind.FUNCTION, SageApiSymbolKind.METHOD, SageApiSymbolKind.CLASS)
        }
        val dynamic = covered.filter { expectedSymbol ->
            index.entry(expectedSymbol.qualifiedName, expectedSymbol.kind)?.let { entry ->
                entry.dynamicity != SageApiDynamicity.STATIC || entry.signatures.any { it.returnType.state == SageTypeState.DYNAMIC }
            } == true
        }
        return SageApiCoverageReport(
            expected = orderedExpected,
            covered = covered,
            missing = missing,
            withoutSignature = withoutSignature,
            dynamic = dynamic,
            conflicts = normalizationDiagnostics.filter { it.kind == SageApiDiagnosticKind.CONFLICT },
        )
    }
}
