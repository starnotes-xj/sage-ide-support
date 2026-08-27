package com.starnotesxj.sageide.completion

import com.intellij.lang.documentation.DocumentationMarkup
import com.intellij.lang.documentation.DocumentationProvider
import com.intellij.openapi.util.text.StringUtil
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.jetbrains.python.codeInsight.PyCustomMember
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyQualifiedNameOwner
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.PyTargetExpression
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
        // Ctrl+Q supplies the documentation target separately from the caret
        // element. Resolve the caret/original side first: if Python already has
        // a physical .py/.pyi declaration, its documentation provider must own
        // the result just as it owns Go to Definition.
        val contextElement = originalElement ?: element
        val contextFile = runCatching { contextElement.containingFile }.getOrNull()
            ?: runCatching { element.containingFile }.getOrNull()
        if (!SageFileUtils.isSageFile(contextFile) && !SageStubIndex.isSageStubFile(contextFile)) return null

        val sourceTargets = sequenceOf(originalElement, element)
            .filterNotNull()
            .toList()
        val resolvedTargets = sourceTargets
            .flatMap { candidate ->
                listOfNotNull(candidate, runCatching { candidate.reference?.resolve() }.getOrNull())
            }
            .distinct()
        val resolvedDeclarations = sourceTargets
            .mapNotNull { candidate -> runCatching { candidate.reference?.resolve() }.getOrNull() }
            .distinct()
        if (resolvedTargets.any(::isNativeDocumentationTarget)) return null

        val query = SageApiIndexService.getInstance().query() ?: return null
        val candidates = sequenceOf(element, originalElement)
            .filterNotNull()
            .flatMap { candidate ->
                sequenceOf(candidate, runCatching { candidate.reference?.resolve() }.getOrNull())
                    .filterNotNull()
            }
            .distinct()
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

        // An indexed synthetic target may be the only available declaration for
        // an external Sage member. Keep its exact qualified-name documentation,
        // but never guess from a tail name when a real declaration was resolved.
        if (resolvedDeclarations.isNotEmpty()) return null

        val shortNames = linkedSetOf<String>()
        candidates.filterIsInstance<PyReferenceExpression>()
            .mapNotNullTo(shortNames) { it.referencedName }
        candidates.mapNotNullTo(shortNames) {
            runCatching { it.text.substringAfterLast('.') }.getOrNull()
                ?.takeIf { IDENTIFIER.matches(it) }
        }
        if (SageFileUtils.isSageFile(contextFile)) {
            shortNames.asSequence()
                .mapNotNull { query.namespaceEntry("sage.all", it) }
                .firstOrNull()
                ?.let { return it }
        }
        return null
    }

    private fun isNativeDocumentationTarget(target: PsiElement): Boolean {
        if (!target.isValid || target is PyCustomMember) return false
        val file = runCatching { target.containingFile }.getOrNull() ?: return false
        val virtualFile = file.virtualFile ?: return false
        if (!virtualFile.isInLocalFileSystem || !virtualFile.extension.orEmpty().equals("py", ignoreCase = true) &&
            !virtualFile.extension.orEmpty().equals("pyi", ignoreCase = true)
        ) return false
        return target is PyFunction || target is PyClass || target is PyTargetExpression ||
            target is PyQualifiedNameOwner
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
