package com.starnotesxj.sageide.completion

import com.intellij.lang.documentation.DocumentationMarkup
import com.intellij.lang.documentation.DocumentationProvider
import com.intellij.openapi.editor.colors.TextAttributesKey
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.text.StringUtil
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.PythonDocumentationHighlightingService
import com.jetbrains.python.documentation.PythonDocumentationProvider
import com.jetbrains.python.highlighting.PyHighlighter
import com.jetbrains.python.psi.PyAnnotationOwner
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.PyDocStringOwner
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyNamedParameter
import com.jetbrains.python.psi.PyParameter
import com.jetbrains.python.psi.PyQualifiedNameOwner
import com.jetbrains.python.psi.PyReferenceExpression
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeState
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex

/**
 * Supplies Quick Documentation from the validated Sage API index and local PSI.
 *
 * Sage index documentation is authoritative for Sage source and Sage SDK stubs;
 * native Python declarations are handled only inside the Sage context gate.
 * Ordinary Python files remain untouched, so Python's native provider keeps its
 * normal behavior outside the Sage boundary.
 */
class SageApiDocumentationProvider : DocumentationProvider {
    override fun getQuickNavigateInfo(element: PsiElement, originalElement: PsiElement?): String? =
        findEntry(element, originalElement)?.let(::renderSignatureHtml)
            ?: findNativeQuickNavigateInfo(element, originalElement)

    override fun generateDoc(element: PsiElement, originalElement: PsiElement?): String? =
        findEntry(element, originalElement)?.let { renderDocumentation(it, element.project) }
            ?: renderNativeDocumentation(element, originalElement)

    /**
     * The Python provider's full doc builder invokes an external formatter and
     * rejects remote-only WSL SDKs.  Its quick-info path is local PSI-only and
     * already carries PyCharm's semantic syntax colors, so keep that part while
     * rendering the docstring ourselves below.
     */
    private fun findNativeQuickNavigateInfo(element: PsiElement, originalElement: PsiElement?): String? {
        val owner = findNativeDocumentationOwner(element, originalElement) ?: return null
        return nativeQuickInfo(owner, originalElement ?: element)
    }

    private fun renderNativeDocumentation(element: PsiElement, originalElement: PsiElement?): String? {
        val owner = findNativeDocumentationOwner(element, originalElement) ?: return null
        val quickInfo = nativeQuickInfo(owner, originalElement ?: element)
        val docString = nativeDocString(owner)
        if (quickInfo.isNullOrBlank() && docString.isNullOrBlank()) return null

        return buildString {
            append(DocumentationMarkup.DEFINITION_START)
            append(quickInfo)
            append(DocumentationMarkup.DEFINITION_END)
            if (!docString.isNullOrBlank()) {
                append(DocumentationMarkup.CONTENT_START)
                append(renderRawDocumentation(docString, element.project))
                append(DocumentationMarkup.CONTENT_END)
            }
        }
    }

    private fun nativeQuickInfo(owner: PyDocStringOwner, context: PsiElement): String =
        runCatching { PythonDocumentationProvider().getQuickNavigateInfo(owner, context) }
            .getOrNull()
            // With no configured local SDK, Python's type evaluator can return
            // an unhelpful ``Any`` signature even when the PSI has annotations.
            // Prefer the declaration-level signature in that case.
            ?.takeIf { !Regex("\\bAny\\b").containsMatchIn(it) }
            ?: renderNativeOwnerSignature(owner)

    private fun renderNativeOwnerSignature(owner: PyDocStringOwner): String {
        val qualifiedName = (owner as? PyQualifiedNameOwner)?.qualifiedName
            ?.takeIf { it.isNotBlank() }
            ?: owner.text
        return when (owner) {
            is PyFunction -> buildString {
                append(styled("def", PyHighlighter.PY_KEYWORD)).append(' ')
                append(styled(qualifiedName, PyHighlighter.PY_FUNC_DEFINITION))
                append(styled("(", PyHighlighter.PY_PARENTHS))
                owner.parameterList.parameters.forEachIndexed { index, parameter ->
                    if (index > 0) append(styled(", ", PyHighlighter.PY_COMMA))
                    append(renderNativeParameter(parameter))
                }
                append(styled(")", PyHighlighter.PY_PARENTHS))
                (owner as? PyAnnotationOwner)?.annotation?.value?.text
                    ?.takeIf { it.isNotBlank() }
                    ?.let {
                        append(styled(" -> ", PyHighlighter.PY_OPERATION_SIGN))
                        append(styled(it, PyHighlighter.PY_ANNOTATION))
                    }
            }

            is PyClass -> buildString {
                append(styled("class", PyHighlighter.PY_KEYWORD)).append(' ')
                append(styled(qualifiedName, PyHighlighter.PY_CLASS_DEFINITION))
            }

            else -> styled(qualifiedName, PyHighlighter.PY_PREDEFINED_DEFINITION)
        }
    }

    private fun renderNativeParameter(parameter: PyParameter): String {
        val named = parameter as? PyNamedParameter
        if (named == null) return styled(parameter.text, PyHighlighter.PY_PARAMETER)

        val text = parameter.text.trim()
        val prefix = when {
            text.startsWith("**") -> "**"
            text.startsWith("*") -> "*"
            else -> ""
        }
        val name = named.name ?: text.removePrefix(prefix).substringBefore(':').substringBefore('=').trim()
        return buildString {
            if (prefix.isNotEmpty()) append(styled(prefix, PyHighlighter.PY_OPERATION_SIGN))
            val isSelf = name == "self" || name == "cls"
            append(styled(name, if (isSelf) PyHighlighter.PY_SELF_PARAMETER else PyHighlighter.PY_PARAMETER))
            named.annotation?.value?.text?.takeIf { it.isNotBlank() }?.let {
                append(styled(": ", PyHighlighter.PY_OPERATION_SIGN))
                append(styled(it, PyHighlighter.PY_ANNOTATION))
            }
            named.defaultValue?.text?.takeIf { it.isNotBlank() }?.let {
                append(styled(" = ", PyHighlighter.PY_OPERATION_SIGN))
                append(styled(it, PyHighlighter.PY_PREDEFINED_USAGE))
            }
        }
    }

    private fun findNativeDocumentationOwner(element: PsiElement, originalElement: PsiElement?): PyDocStringOwner? {
        val contextElement = originalElement ?: element
        val contextFile = runCatching { contextElement.containingFile }.getOrNull()
            ?: runCatching { element.containingFile }.getOrNull()
        if (!SageFileUtils.isSageFile(contextFile) && !SageStubIndex.isSageStubFile(contextFile)) return null

        val candidates = sequenceOf(originalElement, element)
            .filterNotNull()
            .flatMap { candidate ->
                sequenceOf(
                    candidate,
                    runCatching { candidate.reference?.resolve() }.getOrNull(),
                )
            }
            .filterNotNull()
            .distinct()
            .toList()
        // Prefer the resolved declaration itself.  The containing PyFile is
        // also a doc-string owner, but selecting it first would show
        // ``File \"native.sage\"`` instead of the function/class under Ctrl+Q.
        candidates.asSequence()
            .mapNotNull { it as? PyDocStringOwner }
            .firstOrNull()
            ?.let { return it }
        return candidates.asSequence()
            .mapNotNull {
                runCatching { PsiTreeUtil.getParentOfType(it, PyDocStringOwner::class.java, false) }.getOrNull()
            }
            .firstOrNull()
    }

    private fun nativeDocString(owner: PyDocStringOwner): String? {
        val expressionText = runCatching { owner.docStringExpression?.stringValue }.getOrNull()
            ?.takeIf { it.isNotBlank() }
        if (expressionText != null) return expressionText

        val structured = runCatching { owner.structuredDocString }.getOrNull() ?: return null
        return buildString {
            structured.summary.takeIf { it.isNotBlank() }?.let { append(it) }
            structured.description.takeIf { it.isNotBlank() }?.let {
                if (isNotEmpty()) append("\n\n")
                append(it)
            }
            if (structured.parameters.isNotEmpty()) {
                if (isNotEmpty()) append("\n\n")
                append("Parameters:\n")
                structured.parameters.forEach { parameter ->
                    append("- ").append(parameter)
                    structured.getParamDescription(parameter)?.takeIf { it.isNotBlank() }
                        ?.let { append(" -- ").append(it) }
                    append('\n')
                }
            }
            structured.returnDescription?.takeIf { it.isNotBlank() }?.let {
                if (isNotEmpty()) append("\n\n")
                append("Returns:\n").append(it)
            }
        }.takeIf { it.isNotBlank() }
    }

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

    private fun renderDocumentation(entry: SageApiEntry): String = renderDocumentation(entry, null)

    private fun renderDocumentation(entry: SageApiEntry, project: Project?): String = buildString {
        append(DocumentationMarkup.DEFINITION_START)
        append(renderSignatureHtml(entry))
        append(DocumentationMarkup.DEFINITION_END)
        val documentation = entry.documentation
        if (documentation == null) return@buildString

        append(DocumentationMarkup.CONTENT_START)
        documentation.summary
            ?.takeIf { it.isNotBlank() }
            ?.let { append(renderRichText(it, project = project)) }

        documentation.body
            ?.takeIf { it.isNotBlank() && it != documentation.summary }
            ?.let { body ->
                if (documentation.summary?.isNotBlank() == true) append("<br/><br/>")
                val bodyWithoutSummary = documentation.summary
                    ?.takeIf { summary -> body.startsWith(summary) }
                    ?.let { body.removePrefix(it).trimStart() }
                    ?: body
                val parsed = splitSections(bodyWithoutSummary)
                append(renderRichText(parsed.prose, project = project))
                if (parsed.sections.isNotEmpty()) {
                    if (parsed.prose.isNotBlank()) append("<br/><br/>")
                    append(renderSections(parsed.sections, project))
                }
            }

        if (documentation.examples.isNotEmpty()) {
            append("<br/><br/>")
            append(renderSections(listOf(RichSection("Examples", documentation.examples.joinToString("\n"))), project))
        }
        append(DocumentationMarkup.CONTENT_END)
    }

    private fun renderRawDocumentation(text: String, project: Project?): String = buildString {
        val parsed = splitSections(text)
        if (parsed.prose.isNotBlank()) append(renderRichText(parsed.prose, project = project))
        if (parsed.sections.isNotEmpty()) {
            if (parsed.prose.isNotBlank()) append("<br/><br/>")
            append(renderSections(parsed.sections, project))
        }
    }

    private fun renderSections(sections: List<RichSection>, project: Project? = null): String = buildString {
        append(DocumentationMarkup.SECTIONS_START)
        sections.forEach { section ->
            append(DocumentationMarkup.SECTION_HEADER_START)
            append(renderInline(section.title))
            append("</p>")
            append(DocumentationMarkup.SECTION_SEPARATOR)
            append(renderRichText(section.body, preferIndentedCode = section.isExample, project = project))
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

    private fun renderRichText(
        text: String,
        preferIndentedCode: Boolean = false,
        project: Project? = null,
    ): String = buildString {
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
                append(renderCodeBlock(code.joinToString("\n"), fence.groupValues[1], project))
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
                append(renderCodeBlock(code.joinToString("\n"), "", project))
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
                append(renderCodeBlock(code.joinToString("\n"), "", project))
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

    private fun renderCodeBlock(code: String, language: String, project: Project?): String {
        val escaped = escapeCode(code)
        if (project == null) return "<pre><code>$escaped</code></pre>"

        val normalizedLanguage = when (language.trim().lowercase()) {
            "", "sage", "sage3", "py", "python3" -> "Python"
            else -> language.trim()
        }
        val sourceHtml = "<pre data-language=\"${StringUtil.escapeXmlEntities(normalizedLanguage)}\"><code>$escaped</code></pre>"
        val highlighted = runCatching {
            PythonDocumentationHighlightingService.getInstance()
                .highlightCodeBlockInHtml(project, sourceHtml)
        }.getOrNull()
        return highlighted?.takeIf { it.isNotBlank() && it != sourceHtml } ?: sourceHtml
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

    private fun renderSignatureHtml(entry: SageApiEntry): String = buildString {
        val signature = entry.signatures.firstOrNull()
        val isClass = entry.kind == SageApiSymbolKind.CLASS
        append(styled(if (isClass) "class" else "def", PyHighlighter.PY_KEYWORD))
        append(' ')
        append(styled(entry.qualifiedName, if (isClass) PyHighlighter.PY_CLASS_DEFINITION else PyHighlighter.PY_FUNC_DEFINITION))
        if (signature != null) {
            append(styled("(", PyHighlighter.PY_PARENTHS))
            signature.parameters.forEachIndexed { index, parameter ->
                if (index > 0) append(styled(", ", PyHighlighter.PY_COMMA))
                append(renderParameterHtml(parameter))
            }
            append(styled(")", PyHighlighter.PY_PARENTHS))
            signature.returnType.takeIf { it.state == SageTypeState.KNOWN }
                ?.expression
                ?.let {
                    append(styled(" -> ", PyHighlighter.PY_OPERATION_SIGN))
                    append(styled(it, PyHighlighter.PY_ANNOTATION))
                }
        }
    }

    private fun renderParameterHtml(parameter: SageApiParameter): String = buildString {
        if (parameter.variadic) append(styled(if (parameter.keywordOnly) "**" else "*", PyHighlighter.PY_OPERATION_SIGN))
        val isSelf = parameter.name == "self" || parameter.name == "cls"
        append(styled(parameter.name, if (isSelf) PyHighlighter.PY_SELF_PARAMETER else PyHighlighter.PY_PARAMETER))
        parameter.type.takeIf { it.state == SageTypeState.KNOWN }
            ?.expression
            ?.let {
                append(styled(": ", PyHighlighter.PY_OPERATION_SIGN))
                append(styled(it, PyHighlighter.PY_ANNOTATION))
            }
        parameter.defaultValue?.let {
            append(styled(" = ", PyHighlighter.PY_OPERATION_SIGN))
            append(styled(it, PyHighlighter.PY_PREDEFINED_USAGE))
        }
    }

    private fun styled(text: String, key: TextAttributesKey): String {
        val rendered = runCatching {
            PythonDocumentationHighlightingService.getInstance().styledSpan(key, text)
        }.getOrNull()
        return rendered?.takeIf { it != text } ?: StringUtil.escapeXmlEntities(text)
    }

    private fun escapeText(text: String): String =
        StringUtil.escapeXmlEntities(text).replace("\n", "<br/>")

    private fun escapeCode(text: String): String = StringUtil.escapeXmlEntities(text)

    private companion object {
        val IDENTIFIER = Regex("[A-Za-z_][A-Za-z0-9_]*")
        val SECTION_HEADER = Regex("^\\s*([\\p{L}][\\p{L}\\d _/-]{0,48})(:{1,2})\\s*$")
        val FENCE_START = Regex("^\\s*```([A-Za-z0-9_+.-]*)\\s*$")
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
