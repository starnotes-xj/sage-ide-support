package com.starnotesxj.sagemath.sageapi

/**
 * Minimal source-driven extractor for one .pyi module. It favors explicit
 * declarations, preserves unknowns, and never executes imported code.
 */
class SageStubExtractor {
    fun extract(source: SageStubSource): List<SageRawSymbol> {
        val lines = source.text.replace("\r\n", "\n").replace('\r', '\n').lines()
        val result = mutableListOf<SageRawSymbol>()
        val aliases = mutableListOf<SageRawSymbol>()
        val importedTypes = linkedMapOf<String, String>()
        var currentClass: ClassContext? = null
        var pendingDocumentation: SageApiDocumentation? = null
        var pendingProperty = false

        fun takeDocumentation(): SageApiDocumentation? {
            val value = pendingDocumentation
            pendingDocumentation = null
            return value
        }

        lines.forEachIndexed { index, rawLine ->
            val lineNumber = index + 1
            val trimmed = rawLine.trim()
            if (trimmed.isBlank() || trimmed.startsWith("#")) return@forEachIndexed
            if (trimmed.startsWith("\"\"\"") || trimmed.startsWith("'''")) {
                val delimiter = trimmed.take(3)
                val text = trimmed.removePrefix(delimiter).removeSuffix(delimiter).trim()
                if (text.isNotBlank()) {
                    pendingDocumentation = SageApiDocumentation(
                        summary = text.lineSequence().firstOrNull().orEmpty(),
                        body = text,
                    )
                }
                return@forEachIndexed
            }
            if (trimmed == "@property") {
                pendingProperty = true
                return@forEachIndexed
            }
            if (trimmed == "@overload") return@forEachIndexed

            CLASS_PATTERN.matchEntire(trimmed)?.let { match ->
                val name = match.groupValues[1]
                val parents = match.groupValues.getOrNull(2).orEmpty().split(',')
                    .map(String::trim).filter(String::isNotBlank).map { qualifyType(it, importedTypes) }
                result += SageRawSymbol(
                    qualifiedName = "${source.moduleName}.${name}",
                    kind = SageApiSymbolKind.CLASS,
                    source = source.sourceRef(lineNumber),
                    parents = parents,
                    documentation = takeDocumentation(),
                    confidence = SageApiConfidence.HIGH,
                )
                currentClass = ClassContext(name, indentation(rawLine))
                pendingProperty = false
                return@forEachIndexed
            }

            DEF_PATTERN.matchEntire(trimmed)?.let { match ->
                val name = match.groupValues[1]
                val owner = currentClass?.takeIf { indentation(rawLine) > it.indent }
                val qualifiedName = if (owner == null) "${source.moduleName}.${name}" else "${source.moduleName}.${owner.name}.${name}"
                result += SageRawSymbol(
                    qualifiedName = qualifiedName,
                    kind = when {
                        owner == null -> SageApiSymbolKind.FUNCTION
                        pendingProperty -> SageApiSymbolKind.PROPERTY
                        else -> SageApiSymbolKind.METHOD
                    },
                    source = source.sourceRef(lineNumber),
                    signatures = listOf(parseSignature(match.groupValues[2], match.groupValues[3], importedTypes)),
                    documentation = takeDocumentation(),
                    confidence = SageApiConfidence.HIGH,
                )
                pendingProperty = false
                return@forEachIndexed
            }

            FROM_IMPORT_PATTERN.matchEntire(trimmed)?.let { match ->
                val imported = match.groupValues[2]
                val visible = match.groupValues[3].ifBlank { imported }
                importedTypes[visible] = "${match.groupValues[1]}.${imported}"
                importedTypes.putIfAbsent(imported, "${match.groupValues[1]}.${imported}")
                aliases += SageRawSymbol(
                    qualifiedName = "${source.moduleName}.${visible}",
                    kind = SageApiSymbolKind.ALIAS,
                    source = source.sourceRef(lineNumber),
                    aliases = listOf("${match.groupValues[1]}.${imported}"),
                    confidence = SageApiConfidence.HIGH,
                )
                takeDocumentation()
                return@forEachIndexed
            }

            ATTRIBUTE_PATTERN.matchEntire(trimmed)?.let { match ->
                val name = match.groupValues[1]
                val owner = currentClass?.takeIf { indentation(rawLine) > it.indent }
                val qualifiedName = if (owner == null) "${source.moduleName}.${name}" else "${source.moduleName}.${owner.name}.${name}"
                result += SageRawSymbol(
                    qualifiedName = qualifiedName,
                    kind = if (owner == null) SageApiSymbolKind.CONSTANT else SageApiSymbolKind.PROPERTY,
                    source = source.sourceRef(lineNumber),
                    valueType = SageTypeRef.known(qualifyType(match.groupValues[2].trim(), importedTypes)),
                    documentation = takeDocumentation(),
                    confidence = SageApiConfidence.MEDIUM,
                )
                pendingProperty = false
                return@forEachIndexed
            }

            if (indentation(rawLine) <= (currentClass?.indent ?: 0)) currentClass = null
            pendingDocumentation = null
            pendingProperty = false
        }

        return (result + aliases).sortedWith(compareBy<SageRawSymbol> { it.qualifiedName }.thenBy { it.kind.name }.thenBy { it.source.locator })
    }

    private fun parseSignature(
        parametersText: String,
        returnText: String,
        importedTypes: Map<String, String>,
    ): SageApiSignature {
        val parameters = splitTopLevel(parametersText).map(String::trim)
            .filter { it.isNotBlank() && it != "self" && it != "cls" && it != "*" }
            .map { token ->
                val variadic = token.startsWith("*")
                val cleaned = token.removePrefix("*")
                val nameAndType = cleaned.split(':', limit = 2)
                val namePart = nameAndType[0].trim()
                val hasDefault = '=' in namePart
                val name = namePart.substringBefore('=').trim()
                val default = namePart.substringAfter('=', "").trim().takeIf { hasDefault }
                val type = nameAndType.getOrNull(1)?.substringBefore('=').orEmpty().trim()
                SageApiParameter(
                    name = name,
                    type = if (type.isBlank()) SageTypeRef.unknown() else SageTypeRef.known(qualifyType(type, importedTypes)),
                    defaultValue = default,
                    optional = hasDefault,
                    variadic = variadic,
                )
            }
        return SageApiSignature(
            parameters = parameters,
            returnType = returnText.trim().takeIf(String::isNotBlank)?.let { SageTypeRef.known(qualifyType(it, importedTypes)) }
                ?: SageTypeRef.unknown(),
        )
    }

    private fun splitTopLevel(value: String): List<String> {
        val result = mutableListOf<String>()
        var depth = 0
        var start = 0
        value.forEachIndexed { index, character ->
            when (character) {
                '[', '(', '{' -> depth++
                ']', ')', '}' -> depth--
                ',' -> if (depth == 0) {
                    result += value.substring(start, index)
                    start = index + 1
                }
            }
        }
        result += value.substring(start)
        return result
    }

    private fun qualifyType(type: String, importedTypes: Map<String, String> = emptyMap()): String {
        val normalized = type.trim().removePrefix("typing.")
        return importedTypes[normalized] ?: normalized
    }
    private fun indentation(line: String): Int = line.indexOfFirst { !it.isWhitespace() }.coerceAtLeast(0)
    private data class ClassContext(val name: String, val indent: Int)

    private companion object {
        val CLASS_PATTERN = Regex("class\\s+([A-Za-z_]\\w*)(?:\\(([^)]*)\\))?:")
        val DEF_PATTERN = Regex("def\\s+([A-Za-z_]\\w*)\\((.*)\\)\\s*(?:->\\s*([^:]+))?:.*")
        val FROM_IMPORT_PATTERN = Regex("from\\s+([A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)*)\\s+import\\s+([A-Za-z_]\\w*)(?:\\s+as\\s+([A-Za-z_]\\w*))?")
        val ATTRIBUTE_PATTERN = Regex("([A-Za-z_]\\w*)\\s*:\\s*(.+)")
    }
}

data class SageStubSource(
    val moduleName: String,
    val text: String,
    val locator: String,
    val sourceKind: SageApiSourceKind = SageApiSourceKind.STUB,
) {
    init {
        require(moduleName.isNotBlank()) { "Sage stub module name must not be blank" }
        require(locator.isNotBlank()) { "Sage stub locator must not be blank" }
    }

    fun sourceRef(line: Int): SageApiSourceRef = SageApiSourceRef(sourceKind, "${locator}:${line}")
}
