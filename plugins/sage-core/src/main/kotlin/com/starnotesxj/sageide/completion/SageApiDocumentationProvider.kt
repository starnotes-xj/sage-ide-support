package com.starnotesxj.sageide.completion

import com.intellij.lang.documentation.DocumentationMarkup
import com.intellij.lang.documentation.DocumentationProvider
import com.intellij.openapi.util.text.StringUtil
import com.intellij.psi.PsiElement
import com.jetbrains.python.psi.PyQualifiedNameOwner
import com.jetbrains.python.psi.PyReferenceExpression
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageTypeState
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex

/**
 * Supplies Quick Documentation from the validated Sage API index.
 *
 * Native Python documentation remains authoritative for ordinary declarations.
 * This provider is deliberately additive: it answers only for Sage source or
 * Sage SDK stubs, and only when a qualified-name lookup is unambiguous.
 */
class SageApiDocumentationProvider : DocumentationProvider {
    override fun getQuickNavigateInfo(element: PsiElement, originalElement: PsiElement?): String? =
        findEntry(element, originalElement)?.let(::renderSignature)

    override fun generateDoc(element: PsiElement, originalElement: PsiElement?): String? =
        findEntry(element, originalElement)?.let(::renderDocumentation)

    private fun findEntry(element: PsiElement, originalElement: PsiElement?): SageApiEntry? {
        val file = runCatching { element.containingFile }.getOrNull()
            ?: runCatching { originalElement?.containingFile }.getOrNull()
        if (!SageFileUtils.isSageFile(file) && !SageStubIndex.isSageStubFile(file)) return null

        val query = SageApiIndexService.getInstance().query() ?: return null
        val candidates = sequenceOf(element, originalElement)
            .filterNotNull()
            .flatMap { candidate ->
                sequenceOf(candidate, runCatching { candidate.reference?.resolve() }.getOrNull())
                    .filterNotNull()
            }
            .toList()

        candidates.asSequence()
            .mapNotNull { candidate ->
                (candidate as? PyQualifiedNameOwner)?.let {
                    runCatching { it.qualifiedName }.getOrNull()
                }
            }
            .filter { it.isNotBlank() }
            .forEach { qualifiedName ->
                query.find(qualifiedName)?.let { return it }
            }

        val shortNames = linkedSetOf<String>()
        candidates.filterIsInstance<PyReferenceExpression>()
            .mapNotNullTo(shortNames) { it.referencedName }
        candidates.mapNotNullTo(shortNames) {
            runCatching { it.text.substringAfterLast('.') }.getOrNull()
                ?.takeIf { IDENTIFIER.matches(it) }
        }
        if (SageFileUtils.isSageFile(file)) {
            shortNames.asSequence()
                .mapNotNull { query.namespaceEntry("sage.all", it) }
                .firstOrNull()
                ?.let { return it }
        }
        return shortNames.asSequence()
            .map { name -> query.index.entries.filter { it.qualifiedName.substringAfterLast('.') == name } }
            .mapNotNull { matches -> matches.singleOrNull() }
            .firstOrNull()
    }

    private fun renderDocumentation(entry: SageApiEntry): String = buildString {
        append(DocumentationMarkup.DEFINITION_START)
        append(escapeText(renderSignature(entry)))
        append(DocumentationMarkup.DEFINITION_END)
        val documentation = entry.documentation
        if (documentation != null) {
            append(DocumentationMarkup.CONTENT_START)
            documentation.summary?.takeIf { it.isNotBlank() }?.let { append(escapeText(it)) }
            documentation.body
                ?.takeIf { it.isNotBlank() && it != documentation.summary }
                ?.let {
                    if (documentation.summary?.isNotBlank() == true) append("<br/><br/>")
                    append(escapeText(it))
                }
            if (documentation.examples.isNotEmpty()) {
                append("<br/><br/><b>Examples</b><br/>")
                append(documentation.examples.joinToString("<br/>", transform = ::escapeText))
            }
            append(DocumentationMarkup.CONTENT_END)
        }
    }

    private fun renderSignature(entry: SageApiEntry): String {
        val signature = entry.signatures.firstOrNull()
        if (signature == null) return entry.qualifiedName
        val parameters = signature.parameters.joinToString(", ", transform = ::renderParameter)
        val returnType = signature.returnType.takeIf { it.state == SageTypeState.KNOWN }
            ?.expression
            ?.let { " -> $it" }
            .orEmpty()
        return "${entry.qualifiedName}($parameters)$returnType"
    }

    private fun renderParameter(parameter: SageApiParameter): String = buildString {
        if (parameter.variadic) append(if (parameter.keywordOnly) "**" else "*")
        append(parameter.name)
        parameter.type.takeIf { it.state == SageTypeState.KNOWN }
            ?.expression
            ?.let { append(": ").append(it) }
        parameter.defaultValue?.let { append(" = ").append(it) }
    }

    private fun escapeText(text: String): String =
        StringUtil.escapeXmlEntities(text).replace("\n", "<br/>")

    private companion object {
        val IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")
    }
}
