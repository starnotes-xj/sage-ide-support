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
 * Sage index documentation is authoritative for Sage source and Sage SDK stubs.
 * This provider remains isolated from ordinary Python files and only answers
 * when a qualified-name lookup is unambiguous, so Python's native provider is
 * still untouched outside the Sage boundary.
 */
class SageApiDocumentationProvider : DocumentationProvider {
    override fun getQuickNavigateInfo(element: PsiElement, originalElement: PsiElement?): String? =
        findEntry(element, originalElement)?.let(::renderSignature)

    override fun generateDoc(element: PsiElement, originalElement: PsiElement?): String? =
        findEntry(element, originalElement)?.let(::renderDocumentation)

    private fun findEntry(element: PsiElement, originalElement: PsiElement?): SageApiEntry? {
        // Ctrl+Q supplies the documentation target separately from the caret
        // element. Resolve the caret/original side first so Sage SDK stubs can
        // be documented from the immutable index even when the Python plugin
        // has no local SDK configured for the remote/WSL Sage interpreter.
        val contextElement = originalElement ?: element
        val contextFile = runCatching { contextElement.containingFile }.getOrNull()
            ?: runCatching { element.containingFile }.getOrNull()
        if (!SageFileUtils.isSageFile(contextFile) && !SageStubIndex.isSageStubFile(contextFile)) return null

        val sourceTargets = sequenceOf(originalElement, element)
            .filterNotNull()
            .toList()
        val resolvedDeclarations = sourceTargets
            .mapNotNull { candidate -> runCatching { candidate.reference?.resolve() }.getOrNull() }
            .distinct()

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

    private fun renderDocumentation(entry: SageApiEntry): String = buildString {
        append(DocumentationMarkup.DEFINITION_START)
        append(escapeText(renderSignature(entry)))
        append(DocumentationMarkup.DEFINITION_END)
        val documentation = entry.documentation
        if (documentation == null) return@buildString

        append(DocumentationMarkup.CONTENT_START)
        documentation.summary
            ?.takeIf { it.isNotBlank() }
            ?.let { append(renderRichText(it)) }

        documentation.body
            ?.takeIf { it.isNotBlank() && it != documentation.summary }
            ?.let { body ->
                if (documentation.summary?.isNotBlank() == true) append("<br/><br/>")
                val bodyWithoutSummary = documentation.summary
                    ?.takeIf { summary -> body.startsWith(summary) }
                    ?.let { body.removePrefix(it).trimStart() }
                    ?: body
                val parsed = splitSections(bodyWithoutSummary)
                append(renderRichText(parsed.prose))
                if (parsed.sections.isNotEmpty()) {
                    if (parsed.prose.isNotBlank()) append("<br/><br/>")
                    append(renderSections(parsed.sections))
                }
            }

        if (documentation.examples.isNotEmpty()) {
            append("<br/><br/>")
            append(renderSections(listOf(RichSection("Examples", documentation.examples.joinToString("\n")))))
        }
        append(DocumentationMarkup.CONTENT_END)
    }

    private fun renderSections(sections: List<RichSection>): String = buildString {
        append(DocumentationMarkup.SECTIONS_START)
        sections.forEach { section ->
            append(DocumentationMarkup.SECTION_HEADER_START)
            append(renderInline(section.title))
            append("</p>")
            append(DocumentationMarkup.SECTION_SEPARATOR)
            append(renderRichText(section.body, preferIndentedCode = section.isExample))
            append(DocumentationMarkup.SECTION_END)
        }
        append(DocumentationMarkup.SECTIONS_END)
    }

    private fun splitSections(text: String): ParsedDocumentation {
        val prose = mutableListOf<String>()
        val sections = mutableListOf<RichSection>()
        var currentTitle: String? = null
        var currentBody = mutableListOf<String>()

        fun flushSection() {
            val title = currentTitle ?: return
            val body = currentBody.joinToString("\n").trim()
            sections += RichSection(title, body)
            currentTitle = null
            currentBody = mutableListOf()
        }

        text.replace("\r\n", "\n").replace('\r', '\n').lines().forEach { line ->
            val match = SECTION_HEADER.matchEntire(line)
            val title = match?.groupValues?.getOrNull(1)?.trim()
            if (title != null && isSectionTitle(title)) {
                flushSection()
                currentTitle = title
            } else if (currentTitle == null) {
                prose += line
            } else {
                currentBody += line
            }
        }
        flushSection()
        return ParsedDocumentation(prose.joinToString("\n").trim(), sections)
    }

    private fun renderRichText(text: String, preferIndentedCode: Boolean = false): String = buildString {
        val lines = text.replace("\r\n", "\n").replace('\r', '\n').lines()
        val paragraph = mutableListOf<String>()
        var index = 0

        fun flushParagraph() {
            if (paragraph.isEmpty()) return
            append(paragraph.joinToString("<br/>", transform = ::renderInline))
            paragraph.clear()
        }

        while (index < lines.size) {
            val line = lines[index]
            val fence = FENCE_START.matchEntire(line)
            if (fence != null) {
                flushParagraph()
                index++
                val code = mutableListOf<String>()
                while (index < lines.size && !FENCE_END.matches(lines[index])) {
                    code += lines[index]
                    index++
                }
                if (index < lines.size) index++
                append("<pre><code>")
                append(escapeCode(code.joinToString("\n")))
                append("</code></pre>")
                if (index < lines.size && lines[index].isNotBlank()) append("<br/>")
                continue
            }

            if (line.isBlank()) {
                flushParagraph()
                if (index + 1 < lines.size && lines[index + 1].isNotBlank()) append("<br/>")
                index++
                continue
            }

            if (preferIndentedCode && line.startsWith("    ")) {
                flushParagraph()
                val code = mutableListOf<String>()
                while (index < lines.size) {
                    val candidate = lines[index]
                    if (candidate.isBlank()) {
                        code += ""
                        index++
                    } else if (candidate.startsWith("    ")) {
                        code += candidate.removePrefix("    ")
                        index++
                    } else {
                        break
                    }
                }
                while (code.lastOrNull() == "") code.removeAt(code.lastIndex)
                append("<pre><code>")
                append(escapeCode(code.joinToString("\n")))
                append("</code></pre>")
                continue
            }

            if (line.trimEnd().endsWith("::") && index + 1 < lines.size && lines[index + 1].startsWith("    ")) {
                paragraph += line.trimEnd().removeSuffix(":")
                flushParagraph()
                val code = mutableListOf<String>()
                index++
                while (index < lines.size) {
                    val candidate = lines[index]
                    if (candidate.isBlank()) {
                        code += ""
                        index++
                    } else if (candidate.startsWith("    ")) {
                        code += candidate.removePrefix("    ")
                        index++
                    } else {
                        break
                    }
                }
                while (code.lastOrNull() == "") code.removeAt(code.lastIndex)
                append("<pre><code>")
                append(escapeCode(code.joinToString("\n")))
                append("</code></pre>")
                continue
            }

            if (line.trimStart().startsWith("- ") || line.trimStart().startsWith("* ")) {
                flushParagraph()
                append("<ul>")
                while (index < lines.size &&
                    (lines[index].trimStart().startsWith("- ") || lines[index].trimStart().startsWith("* "))
                ) {
                    val item = lines[index].trimStart().drop(2)
                    append("<li>").append(renderInline(item)).append("</li>")
                    index++
                }
                append("</ul>")
                continue
            }

            paragraph += line.trim()
            index++
        }
        flushParagraph()
    }

    private fun renderInline(text: String): String {
        var rendered = escapeText(text)
        rendered = DOUBLE_INLINE_CODE.replace(rendered) { "<code>${it.groupValues[1]}</code>" }
        rendered = INLINE_CODE.replace(rendered) { "<code>${it.groupValues[1]}</code>" }
        rendered = BOLD.replace(rendered) { "<b>${it.groupValues[1]}</b>" }
        return rendered
    }

    private fun isSectionTitle(title: String): Boolean =
        title.trim().lowercase() in SECTION_TITLES

    private data class ParsedDocumentation(
        val prose: String,
        val sections: List<RichSection>,
    )

    private data class RichSection(
        val title: String,
        val body: String,
    ) {
        val isExample: Boolean
            get() = title.trim().lowercase() in EXAMPLE_TITLES
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

    private fun escapeCode(text: String): String = StringUtil.escapeXmlEntities(text)

    private companion object {
        val IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")
        val SECTION_HEADER = Regex("^\\s*([\\p{L}][\\p{L}\\d _/-]{0,48})(:{1,2})\\s*$")
        val FENCE_START = Regex("^\\s*```(?:[A-Za-z0-9_+.-]+)?\\s*$")
        val FENCE_END = Regex("^\\s*```\\s*$")
        val DOUBLE_INLINE_CODE = Regex("``([^`\\n]+)``")
        val INLINE_CODE = Regex("`([^`\\n]+)`")
        val BOLD = Regex("\\*\\*([^*\\n]+)\\*\\*")
        val SECTION_TITLES = setOf(
            "parameters", "parameter", "args", "arguments", "keyword arguments", "keywords",
            "input", "inputs", "output", "outputs", "return", "returns", "return value", "yields",
            "raises", "raised exceptions", "exceptions", "examples", "example", "tests", "test",
            "notes", "note", "remarks", "remark", "see also", "references", "reference", "authors",
            "author", "attributes", "attribute", "warnings", "warning", "algorithm", "algorithms",
            "options", "option", "variables", "variable", "constraints", "constraint", "implementation",
            "definition", "signature", "kwds", "kwargs",
            "参数", "参数列表", "关键字参数", "返回", "返回值", "产出", "异常", "示例",
            "测试", "注意", "备注", "另见", "参考", "属性", "警告", "算法", "实现", "定义",
        )
        val EXAMPLE_TITLES = setOf("examples", "example", "示例")
    }
}
