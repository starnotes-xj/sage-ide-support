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
        val typeParameterConstructors = linkedMapOf(
            "TypeVar" to SageApiTypeParameterKind.TYPE_VARIABLE,
            "ParamSpec" to SageApiTypeParameterKind.PARAM_SPEC,
            "typing.TypeVar" to SageApiTypeParameterKind.TYPE_VARIABLE,
            "typing.ParamSpec" to SageApiTypeParameterKind.PARAM_SPEC,
            "typing_extensions.TypeVar" to SageApiTypeParameterKind.TYPE_VARIABLE,
            "typing_extensions.ParamSpec" to SageApiTypeParameterKind.PARAM_SPEC,
        )
        val declaredTypeParameters = linkedMapOf<String, SageApiTypeParameter>()
        val classStack = mutableListOf<ClassContext>()
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

            val lineIndent = indentation(rawLine)
            while (classStack.lastOrNull()?.indent?.let { it >= lineIndent } == true) {
                classStack.removeAt(classStack.lastIndex)
            }

            if (lineIndent == 0) {
                typeParameterDeclaration(trimmed, importedTypes, typeParameterConstructors)?.let { (name, declaration) ->
                    declaredTypeParameters[name] = declaration
                    return@forEachIndexed
                }
            }

            CLASS_PATTERN.matchEntire(trimmed)?.let { match ->
                val name = match.groupValues[1]
                val parents = match.groupValues.getOrNull(2).orEmpty().split(',')
                    .map(String::trim).filter(String::isNotBlank).map { qualifyType(it, importedTypes) }
                val qualifiedName = classStack.lastOrNull()?.let { "${it.qualifiedName}.${name}" }
                    ?: "${source.moduleName}.${name}"
                result += SageRawSymbol(
                    qualifiedName = qualifiedName,
                    kind = SageApiSymbolKind.CLASS,
                    source = source.sourceRef(lineNumber),
                    parents = parents,
                    documentation = takeDocumentation(),
                    confidence = SageApiConfidence.HIGH,
                )
                classStack += ClassContext(name, qualifiedName, lineIndent)
                pendingProperty = false
                return@forEachIndexed
            }

            DEF_PATTERN.matchEntire(trimmed)?.let { match ->
                val name = match.groupValues[1]
                val owner = classStack.lastOrNull()
                val qualifiedName = owner?.let { "${it.qualifiedName}.${name}" } ?: "${source.moduleName}.${name}"
                result += SageRawSymbol(
                    qualifiedName = qualifiedName,
                    kind = when {
                        owner == null -> SageApiSymbolKind.FUNCTION
                        pendingProperty -> SageApiSymbolKind.PROPERTY
                        else -> SageApiSymbolKind.METHOD
                    },
                    source = source.sourceRef(lineNumber),
                    signatures = listOf(parseSignature(match.groupValues[2], match.groupValues[3], importedTypes, declaredTypeParameters)),
                    documentation = takeDocumentation(),
                    confidence = SageApiConfidence.HIGH,
                )
                pendingProperty = false
                return@forEachIndexed
            }

            IMPORT_MODULE_PATTERN.matchEntire(trimmed)?.let { match ->
                val module = match.groupValues[1]
                val visible = match.groupValues[2].ifBlank { module.substringAfterLast('.') }
                importedTypes[visible] = module
                if (module == "typing" || module == "typing_extensions") {
                    typeParameterConstructors["${visible}.TypeVar"] = SageApiTypeParameterKind.TYPE_VARIABLE
                    typeParameterConstructors["${visible}.ParamSpec"] = SageApiTypeParameterKind.PARAM_SPEC
                }
                return@forEachIndexed
            }

            FROM_IMPORT_PATTERN.matchEntire(trimmed)?.let { match ->
                val imported = match.groupValues[2]
                val visible = match.groupValues[3].ifBlank { imported }
                importedTypes[visible] = "${match.groupValues[1]}.${imported}"
                importedTypes.putIfAbsent(imported, "${match.groupValues[1]}.${imported}")
                if (match.groupValues[1] == "typing" || match.groupValues[1] == "typing_extensions") {
                    when (imported) {
                        "TypeVar" -> typeParameterConstructors[visible] = SageApiTypeParameterKind.TYPE_VARIABLE
                        "ParamSpec" -> typeParameterConstructors[visible] = SageApiTypeParameterKind.PARAM_SPEC
                    }
                }
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
                val owner = classStack.lastOrNull()
                val qualifiedName = owner?.let { "${it.qualifiedName}.${name}" } ?: "${source.moduleName}.${name}"
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

            pendingDocumentation = null
            pendingProperty = false
        }

        return (result + aliases).sortedWith(compareBy<SageRawSymbol> { it.qualifiedName }.thenBy { it.kind.name }.thenBy { it.source.locator })
    }

    private fun parseSignature(
        parametersText: String,
        returnText: String,
        importedTypes: Map<String, String>,
        moduleTypeParameters: Map<String, SageApiTypeParameter> = emptyMap(),
    ): SageApiSignature {
        var keywordOnly = false
        val referencedTypeParameters = referencedTypeParameters(parametersText, returnText, moduleTypeParameters)
        val declaredTypeParameters = moduleTypeParameters.values
            .filter { it.name in referencedTypeParameters }
            .toMutableList()
        if ("Self" in referencedTypeParameters) {
            declaredTypeParameters += SageApiTypeParameter("Self", SageApiTypeParameterKind.SELF)
        }
        val parameters = mutableListOf<SageApiParameter>()
        splitTopLevel(parametersText).map(String::trim)
            .filter { it.isNotBlank() && it != "self" && it != "cls" }
            .forEach { token ->
                when (token) {
                    "/" -> parameters.indices.forEach { index ->
                        val parameter = parameters[index]
                        if (!parameter.keywordOnly && !parameter.variadic) {
                            parameters[index] = parameter.copy(positionalOnly = true)
                        }
                    }
                    "*" -> keywordOnly = true
                    else -> {
                        val positionalContainer = token.startsWith("*") && !token.startsWith("**")
                        val keywordContainer = token.startsWith("**")
                        val variadic = positionalContainer || keywordContainer
                        if (positionalContainer) keywordOnly = true
                        val cleaned = token.removePrefix("**").removePrefix("*")
                        val nameAndType = cleaned.split(':', limit = 2)
                        val namePart = nameAndType[0].trim()
                        val typeAndDefault = nameAndType.getOrNull(1)?.trim().orEmpty()
                        val hasDefault = '=' in namePart || '=' in typeAndDefault
                        val name = namePart.substringBefore('=').trim()
                        val default = when {
                            '=' in namePart -> namePart.substringAfter('=').trim()
                            '=' in typeAndDefault -> typeAndDefault.substringAfter('=').trim()
                            else -> null
                        }
                        val type = typeAndDefault.substringBefore('=').trim()
                        val qualifiedType = if (type.isBlank()) SageTypeRef.unknown() else SageTypeRef.known(qualifyType(type, importedTypes))
                        parameters += SageApiParameter(
                            name = name,
                            type = qualifiedType,
                            defaultValue = default,
                            optional = hasDefault,
                            keywordOnly = keywordOnly || keywordContainer,
                            variadic = variadic,
                            positionalOnly = false,
                        )
                    }
                }
            }
        return SageApiSignature(
            parameters = parameters,
            returnType = returnText.trim().takeIf(String::isNotBlank)?.let { SageTypeRef.known(qualifyType(it, importedTypes)) }
                ?: SageTypeRef.unknown(),
            typeParameters = declaredTypeParameters,
        )
    }

    private fun referencedTypeParameters(
        parametersText: String,
        returnText: String,
        moduleTypeParameters: Map<String, SageApiTypeParameter>,
    ): Set<String> {
        val declaredNames = moduleTypeParameters.keys + setOf("Self", "typing.Self", "typing_extensions.Self")
        val annotations = splitTopLevel(parametersText).mapNotNull { parameterAnnotation(it) } +
            returnText.trim().takeIf(String::isNotBlank).orEmpty()
        val paramSpecNames = moduleTypeParameters.values
            .filter { it.kind == SageApiTypeParameterKind.PARAM_SPEC }
            .map { it.name }
            .toSet()
        return annotations.asSequence()
            .mapNotNull {
                SageTypeRefExpressionParser.parse(
                    it,
                    declaredNames,
                    moduleTypeParameters.values.filter { parameter -> parameter.kind == SageApiTypeParameterKind.PARAM_SPEC }.map { parameter -> parameter.name }.toSet(),
                )
            }
            .flatMap { typeVariables(it).asSequence() }
            .map { if (it.endsWith(".Self")) "Self" else it }
            .filter { it in moduleTypeParameters.keys || it == "Self" }
            .toSet()
    }

    private fun parameterAnnotation(token: String): String? {
        var depth = 0
        var quote: Char? = null
        var escaped = false
        var colon = -1
        var equals = -1
        token.forEachIndexed { index, character ->
            if (quote != null) {
                if (escaped) escaped = false
                else if (character == '\\') escaped = true
                else if (character == quote) quote = null
                return@forEachIndexed
            }
            when (character) {
                '\'', '"' -> quote = character
                '[', '(', '{' -> depth++
                ']', ')', '}' -> depth--
                ':' -> if (depth == 0 && colon < 0) colon = index
                '=' -> if (depth == 0 && colon >= 0 && equals < 0) equals = index
            }
        }
        if (colon < 0) return null
        return token.substring(colon + 1, if (equals < 0) token.length else equals).trim()
            .takeIf(String::isNotBlank)
    }

    private fun typeParameterDeclaration(
        text: String,
        importedTypes: Map<String, String>,
        constructors: Map<String, SageApiTypeParameterKind>,
    ): Pair<String, SageApiTypeParameter>? {
        val match = TYPE_PARAMETER_ASSIGNMENT_PATTERN.matchEntire(text) ?: return null
        val constructor = match.groupValues[2]
        val kind = constructors[constructor]
            ?: constructors[importedTypes[constructor].orEmpty()]
            ?: return null
        val args = splitTopLevel(match.groupValues[3]).map(String::trim)
        val named = args.drop(1).mapNotNull(::namedArgument)
        val bound = named.firstOrNull { it.first == "bound" }?.second
        val constraints = args.drop(1)
            .filter { token ->
                val name = namedArgument(token)?.first
                name == null || name !in setOf("bound", "default", "covariant", "contravariant", "infer_variance")
            }
            .map { token -> SageTypeRef.known(qualifyType(token.trim('\"', '\''), importedTypes)) }
        return match.groupValues[1] to SageApiTypeParameter(
            name = match.groupValues[1],
            kind = kind,
            bound = bound?.takeIf(String::isNotBlank)?.let { SageTypeRef.known(qualifyType(it.trim('\"', '\''), importedTypes)) },
            constraints = constraints,
        )
    }

    private fun namedArgument(token: String): Pair<String, String>? {
        val equals = topLevelEquals(token)
        if (equals < 0) return null
        return token.substring(0, equals).trim() to token.substring(equals + 1).trim()
    }

    private fun topLevelEquals(value: String): Int {
        var depth = 0
        var quote: Char? = null
        var escaped = false
        value.forEachIndexed { index, character ->
            if (quote != null) {
                if (escaped) escaped = false
                else if (character == '\\') escaped = true
                else if (character == quote) quote = null
                return@forEachIndexed
            }
            when (character) {
                '\'', '"' -> quote = character
                '[', '(', '{' -> depth++
                ']', ')', '}' -> depth--
                '=' -> if (depth == 0) return index
            }
        }
        return -1
    }

    private fun typeVariables(expression: SageTypeExpression): Set<String> = when (expression) {
        is SageTypeExpression.TypeVariable -> setOf(expression.name)
        is SageTypeExpression.Generic -> expression.arguments.fold(linkedSetOf()) { result, argument ->
            result += typeVariables(argument)
            result
        }
        is SageTypeExpression.Union -> expression.members.fold(linkedSetOf()) { result, member ->
            result += typeVariables(member)
            result
        }
        is SageTypeExpression.Optional -> typeVariables(expression.element)
        is SageTypeExpression.ParamSpecAccess -> setOf(expression.name)
        is SageTypeExpression.Callable -> buildSet {
            expression.parameters.orEmpty().forEach { addAll(typeVariables(it)) }
            addAll(typeVariables(expression.returnType))
        }
        is SageTypeExpression.Name,
        SageTypeExpression.NoneType,
        SageTypeExpression.EllipsisType,
        is SageTypeExpression.Literal -> emptySet()
    }

    private fun splitTopLevel(value: String): List<String> {
        val result = mutableListOf<String>()
        var depth = 0
        var start = 0
        var quote: Char? = null
        var escaped = false
        value.forEachIndexed { index, character ->
            if (quote != null) {
                if (escaped) {
                    escaped = false
                } else if (character == '\\') {
                    escaped = true
                } else if (character == quote) {
                    quote = null
                }
                return@forEachIndexed
            }
            when (character) {
                '\'', '"' -> quote = character
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
    private data class ClassContext(val name: String, val qualifiedName: String, val indent: Int)

    private companion object {
        val TYPE_PARAMETER_ASSIGNMENT_PATTERN = Regex("([A-Za-z_]\\w*)\\s*=\\s*([A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)?)\\s*\\((.*)\\)")
        val CLASS_PATTERN = Regex("class\\s+([A-Za-z_]\\w*)(?:\\(([^)]*)\\))?:")
        val DEF_PATTERN = Regex("def\\s+([A-Za-z_]\\w*)\\((.*)\\)\\s*(?:->\\s*([^:]+))?:.*")
        val FROM_IMPORT_PATTERN = Regex("from\\s+([A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)*)\\s+import\\s+([A-Za-z_]\\w*)(?:\\s+as\\s+([A-Za-z_]\\w*))?")
        val IMPORT_MODULE_PATTERN = Regex("import\\s+([A-Za-z_]\\w*(?:\\.[A-Za-z_]\\w*)*)(?:\\s+as\\s+([A-Za-z_]\\w*))?")
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
