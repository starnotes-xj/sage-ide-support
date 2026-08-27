package com.starnotesxj.sagemath.sageapi

const val SAGE_API_SCHEMA_VERSION: Int = 1

/** SageMath and Python versions are part of the index identity. */
data class SageApiVersion(
    val sage: String,
    val python: String,
) {
    init {
        require(sage.isNotBlank()) { "SageMath version must not be blank" }
        require(python.isNotBlank()) { "Python version must not be blank" }
    }
}

enum class SageApiSymbolKind {
    MODULE,
    CLASS,
    FUNCTION,
    METHOD,
    PROPERTY,
    CONSTANT,
    ALIAS,
}

enum class SageApiSourceKind {
    RUNTIME,
    STUB,
    SIGNATURE,
    DOCUMENTATION,
    USER_STUB,
    PROBE,
}

data class SageApiSourceRef(
    val kind: SageApiSourceKind,
    val locator: String,
    val digest: String? = null,
) {
    init {
        require(locator.isNotBlank()) { "Sage API source locator must not be blank" }
        require(digest == null || digest.matches(Regex("[0-9a-fA-F]{64}"))) {
            "Sage API source digest must be SHA-256 when present"
        }
    }
}

enum class SageTypeState {
    KNOWN,
    UNKNOWN,
    DYNAMIC,
}

data class SageTypeRef(
    val expression: String? = null,
    val state: SageTypeState = if (expression == null) SageTypeState.UNKNOWN else SageTypeState.KNOWN,
) {
    init {
        require(state != SageTypeState.KNOWN || !expression.isNullOrBlank()) {
            "Known Sage type references require an expression"
        }
        require(expression == null || expression.none { it.isISOControl() }) {
            "Sage type expressions must not contain control characters"
        }
    }

    companion object {
        fun known(expression: String): SageTypeRef = SageTypeRef(expression.trim(), SageTypeState.KNOWN)

        fun unknown(): SageTypeRef = SageTypeRef(null, SageTypeState.UNKNOWN)

        fun dynamic(): SageTypeRef = SageTypeRef(null, SageTypeState.DYNAMIC)
    }
}

enum class SageApiDynamicity {
    STATIC,
    DYNAMIC,
    UNKNOWN,
}

enum class SageApiConfidence {
    HIGH,
    MEDIUM,
    LOW,
    UNKNOWN,
}

data class SageApiParameter(
    val name: String,
    val type: SageTypeRef = SageTypeRef.unknown(),
    val defaultValue: String? = null,
    val optional: Boolean = defaultValue != null,
    val keywordOnly: Boolean = false,
    val variadic: Boolean = false,
    val positionalOnly: Boolean = false,
) {
    init {
        require(name.isNotBlank()) { "Sage API parameter name must not be blank" }
        require(name.none { it.isISOControl() }) { "Sage API parameter name contains a control character" }
    }
}

enum class SageApiTypeParameterKind {
    TYPE_VARIABLE,
    SELF,
    PARAM_SPEC,
}

data class SageApiTypeParameter(
    val name: String,
    val kind: SageApiTypeParameterKind = SageApiTypeParameterKind.TYPE_VARIABLE,
    val bound: SageTypeRef? = null,
    val constraints: List<SageTypeRef> = emptyList(),
) {
    init {
        require(name.isNotBlank()) { "Sage API type parameter name must not be blank" }
        require(name.none { it.isISOControl() }) { "Sage API type parameter name contains a control character" }
        require(kind != SageApiTypeParameterKind.SELF || name == "Self") {
            "Self type parameters must be named Self"
        }
        require(bound == null || constraints.isEmpty()) {
            "A Sage API type parameter cannot have both a bound and constraints"
        }
    }
}

enum class SageApiReturnEvidenceKind {
    TRUSTED_MANIFEST,
    TRUSTED_STUB,
}

data class SageApiReturnEvidence(
    val kind: SageApiReturnEvidenceKind,
    val returnType: SageTypeRef,
    val source: SageApiSourceRef,
) {
    init {
        require(source.locator.isNotBlank()) { "Trusted return evidence requires a source locator" }
        require(source.digest != null) { "Trusted return evidence requires a source digest" }
    }
}

data class SageApiSignature(
    val parameters: List<SageApiParameter> = emptyList(),
    val returnType: SageTypeRef = SageTypeRef.unknown(),
    /** Explicitly declared generic variables in this signature's scope. */
    val typeParameters: List<SageApiTypeParameter> = emptyList(),
    /** Auditable, independent return proofs; never replaces [returnType]. */
    val trustedReturnEvidence: List<SageApiReturnEvidence> = emptyList(),
) {
    init {
        require(typeParameters.map { it.name }.toSet().size == typeParameters.size) {
            "Sage API signature type parameter names must be unique"
        }
        require(trustedReturnEvidence.map { evidence ->
            evidence.kind to evidence.source.kind to evidence.source.locator to evidence.source.digest
        }.toSet().size == trustedReturnEvidence.size) {
            "Sage API signature trusted return evidence sources must be unique"
        }
        require(trustedReturnEvidence.all { it.returnType.state == SageTypeState.KNOWN && !it.returnType.expression.isNullOrBlank() }) {
            "Trusted return evidence must contain only KNOWN return types"
        }
        require(trustedReturnEvidence.map { it.returnType.expression!!.trim() }.toSet().size <= 1) {
            "Sage API signature trusted return evidence must agree"
        }
        require(trustedReturnEvidence.none { it.kind == SageApiReturnEvidenceKind.TRUSTED_MANIFEST && it.source.kind != SageApiSourceKind.SIGNATURE }) {
            "Trusted manifest return evidence must cite a signature source"
        }
    }
    companion object {
        fun dynamic(): SageApiSignature = SageApiSignature(returnType = SageTypeRef.dynamic())
    }
}

data class SageApiDocumentation(
    val summary: String? = null,
    val body: String? = null,
    val examples: List<String> = emptyList(),
)

data class SageRawSymbol(
    val qualifiedName: String,
    val kind: SageApiSymbolKind,
    val source: SageApiSourceRef,
    val signatures: List<SageApiSignature> = emptyList(),
    val valueType: SageTypeRef? = null,
    val parents: List<String> = emptyList(),
    val protocols: List<String> = emptyList(),
    val aliases: List<String> = emptyList(),
    val documentation: SageApiDocumentation? = null,
    val dynamicity: SageApiDynamicity = SageApiDynamicity.STATIC,
    val confidence: SageApiConfidence = SageApiConfidence.UNKNOWN,
) {
    init {
        require(qualifiedName.isNotBlank()) { "Sage API qualified name must not be blank" }
        require(qualifiedName.none { it.isISOControl() }) { "Sage API qualified name contains a control character" }
    }
}

data class SageApiEntry(
    val qualifiedName: String,
    val kind: SageApiSymbolKind,
    val signatures: List<SageApiSignature> = emptyList(),
    val valueType: SageTypeRef? = null,
    val parents: List<String> = emptyList(),
    val protocols: List<String> = emptyList(),
    val aliases: List<String> = emptyList(),
    val documentation: SageApiDocumentation? = null,
    val dynamicity: SageApiDynamicity = SageApiDynamicity.UNKNOWN,
    val confidence: SageApiConfidence = SageApiConfidence.UNKNOWN,
    val sources: List<SageApiSourceRef> = emptyList(),
) {
    val moduleName: String
        get() = qualifiedName.substringBeforeLast('.', qualifiedName)

    val ownerName: String?
        get() = qualifiedName.substringBeforeLast('.', "").takeIf { it.isNotBlank() }
}

data class SageApiIndex(
    val sageVersion: String,
    val pythonVersion: String,
    val entries: List<SageApiEntry>,
    val generatorVersion: String = "sage-api-index/0.1",
    val sourceDigests: Map<String, String> = emptyMap(),
    val schemaVersion: Int = SAGE_API_SCHEMA_VERSION,
) {
    init {
        require(schemaVersion == SAGE_API_SCHEMA_VERSION) { "Unsupported Sage API schema version: $schemaVersion" }
        require(sageVersion.isNotBlank()) { "SageMath version must not be blank" }
        require(pythonVersion.isNotBlank()) { "Python version must not be blank" }
        require(generatorVersion.isNotBlank()) { "Sage API generator version must not be blank" }
        require(entries.map { it.qualifiedName to it.kind }.toSet().size == entries.size) {
            "Sage API index contains duplicate qualified-name/kind entries"
        }
        sourceDigests.forEach { (locator, digest) ->
            require(locator.isNotBlank()) { "Sage API source digest locator must not be blank" }
            require(digest.matches(Regex("[0-9a-fA-F]{64}"))) {
                "Sage API source digest must be SHA-256: $locator"
            }
        }
    }

    fun entry(qualifiedName: String, kind: SageApiSymbolKind? = null): SageApiEntry? =
        entries.firstOrNull { it.qualifiedName == qualifiedName && (kind == null || it.kind == kind) }
}

enum class SageApiDiagnosticKind {
    DUPLICATE,
    CONFLICT,
    INVALID,
    UNRESOLVED_ALIAS,
}

data class SageApiDiagnostic(
    val kind: SageApiDiagnosticKind,
    val qualifiedName: String,
    val message: String,
    val sources: List<SageApiSourceRef> = emptyList(),
)

data class SageApiNormalizationResult(
    val index: SageApiIndex,
    val diagnostics: List<SageApiDiagnostic>,
)

data class SageApiExpectedSymbol(
    val qualifiedName: String,
    val kind: SageApiSymbolKind,
)

data class SageApiCoverageReport(
    val expected: List<SageApiExpectedSymbol>,
    val covered: List<SageApiExpectedSymbol>,
    val missing: List<SageApiExpectedSymbol>,
    val withoutSignature: List<SageApiExpectedSymbol>,
    val dynamic: List<SageApiExpectedSymbol>,
    val conflicts: List<SageApiDiagnostic>,
) {
    val expectedCount: Int
        get() = expected.size

    val coveredCount: Int
        get() = covered.size

    val coverageRatio: Double
        get() = if (expected.isEmpty()) 1.0 else coveredCount.toDouble() / expectedCount

    val isComplete: Boolean
        get() = missing.isEmpty() && conflicts.isEmpty()

    fun render(): String = buildString {
        append("expected=").append(expectedCount)
        append(" covered=").append(coveredCount)
        append(" missing=").append(missing.size)
        append(" withoutSignature=").append(withoutSignature.size)
        append(" dynamic=").append(dynamic.size)
        append(" conflicts=").append(conflicts.size)
        append(" coverage=").append("%.4f".format(java.util.Locale.ROOT, coverageRatio))
    }
}
