package com.starnotesxj.sageide.completion

import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.psi.PsiManager
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.PyFunction
import com.starnotesxj.sagemath.sageapi.SageApiDocumentation
import com.starnotesxj.sagemath.sageapi.SageApiEntry
import com.starnotesxj.sagemath.sageapi.SageApiIndex
import com.starnotesxj.sagemath.sageapi.SageApiParameter
import com.starnotesxj.sagemath.sageapi.SageApiSignature
import com.starnotesxj.sagemath.sageapi.SageApiSourceKind
import com.starnotesxj.sagemath.sageapi.SageApiSourceRef
import com.starnotesxj.sagemath.sageapi.SageApiSymbolKind
import com.starnotesxj.sagemath.sageapi.SageTypeRef

/**
 * Goal C's PSI data source: walks the local stub-tree mirror through the
 * platform and builds the same [SageApiIndex] the JSON sidecar used to
 * carry.  Every rich consumer (operator reflection, member merging, type
 * lowering) keeps consuming
 * [com.starnotesxj.sagemath.sageapi.SageApiIndexQuery] — only the data
 * source changes.
 *
 * Built once per receipt-only sidecar activation on a background thread;
 * the index is immutable afterwards, exactly like the JSON one.
 */
object SagePsiApiIndexFactory {

    private val LOG = Logger.getInstance(SagePsiApiIndexFactory::class.java)

    /**
     * @param mirror the local stub-tree root (a synthetic library source root)
     * @param sageVersion the sidecar's declared Sage version
     * @param pythonVersion runtime python version string ("3.13")
     */
    fun build(project: Project, mirror: VirtualFile, sageVersion: String, pythonVersion: String): SageApiIndex? {
        val started = System.currentTimeMillis()
        // A freshly installed mirror is not in the VFS yet.  The caller
        // refreshes the tree OUTSIDE the read action (a synchronous refresh
        // under a read lock is a platform error); here we only walk.
        val manager = PsiManager.getInstance(project)
        val entries = mutableListOf<SageApiEntry>()
        val queue = ArrayDeque<VirtualFile>()
        queue.add(mirror)
        var stubFiles = 0
        while (queue.isNotEmpty()) {
            val children = queue.removeFirst().children
            for (child in children) {
                when {
                    child.isDirectory -> queue.add(child)
                    child.name.endsWith(".pyi") || child.name.endsWith(".py") -> {
                        val file = manager.findFile(child) as? PyFile ?: continue
                        stubFiles += 1
                        collectFile(file, entries)
                    }
                }
            }
        }
        if (entries.isEmpty()) {
            LOG.warn("Sage PSI index: mirror produced no entries under " + mirror.url)
            return null
        }
        // The same class can be visible through both the mirror and other
        // library roots; keep one entry per (qualifiedName, kind).
        val deduplicated = entries.distinctBy { it.qualifiedName to it.kind }
        LOG.info(
            "Sage PSI index built: ${deduplicated.size} entries from $stubFiles files " +
                "in ${System.currentTimeMillis() - started} ms",
        )
        return SageApiIndex(
            sageVersion = sageVersion,
            pythonVersion = pythonVersion,
            entries = deduplicated,
            generatorVersion = "sage-psi-index/1.0",
        )
    }

    private fun collectFile(file: PyFile, entries: MutableList<SageApiEntry>) {
        val module = moduleQualifiedName(file) ?: return
        for (klass in file.topLevelClasses) {
            collectClass(module, klass, entries)
        }
        for (function in file.topLevelFunctions) {
            val name = function.name ?: continue
            val qualified = "$module.$name"
            entries += SageApiEntry(
                qualifiedName = qualified,
                kind = SageApiSymbolKind.FUNCTION,
                signatures = listOfNotNull(signature(function)),
                documentation = documentation(function.docStringExpression, name),
                sources = listOf(SageApiSourceRef(SageApiSourceKind.STUB, qualified)),
            )
        }
    }

    /** ``sage.rings.integer`` from a mirror file at ``sage/rings/integer.pyi``. */
    private fun moduleQualifiedName(file: PyFile): String? {
        val fileName = file.virtualFile?.name ?: return null
        val moduleFile = fileName.removeSuffix(".pyi").removeSuffix(".py")
        if (moduleFile.isEmpty() || moduleFile == "__init__") return null
        val parts = ArrayDeque<String>()
        parts.addFirst(moduleFile)
        var directory = file.virtualFile?.parent ?: return null
        while (directory.isDirectory && directory.name != "sage") {
            parts.addFirst(directory.name)
            directory = directory.parent ?: return null
        }
        if (directory.name != "sage") return null
        return (listOf("sage") + parts).joinToString(".")
    }

    private fun collectClass(owner: String, klass: PyClass, entries: MutableList<SageApiEntry>) {
        val name = klass.name ?: return
        val qualified = if (owner.endsWith(".$name") || owner == name) name else "$owner.$name"
        entries += SageApiEntry(
            qualifiedName = qualified,
            kind = SageApiSymbolKind.CLASS,
            parents = klass.superClassExpressions.map { expression ->
                expression.text.replace("\\s+".toRegex(), "")
            }.map { textual -> resolveBaseToQualifiedName(klass, textual) ?: textual },
            documentation = documentation(klass.docStringExpression, name),
            sources = listOf(SageApiSourceRef(SageApiSourceKind.STUB, qualified)),
        )
        for (method in klass.methods) {
            val methodName = method.name ?: continue
            val methodQualified = "$qualified.$methodName"
            entries += SageApiEntry(
                qualifiedName = methodQualified,
                kind = if (isPropertyDecorator(method)) SageApiSymbolKind.PROPERTY else SageApiSymbolKind.METHOD,
                signatures = listOfNotNull(signature(method)),
                documentation = documentation(method.docStringExpression, methodName),
                sources = listOf(SageApiSourceRef(SageApiSourceKind.STUB, methodQualified)),
            )
        }
        for (nested in klass.nestedClasses) {
            collectClass(qualified, nested, entries)
        }
    }

    /**
     * A base spelled ``EllipticCurvePoint`` resolves through the class's own
     * qualified name or the same-module class list; anything else keeps its
     * textual form (the query layer handles sage.* parents directly).
     */
    private fun resolveBaseToQualifiedName(klass: PyClass, textual: String): String? {
        val qualified = klass.qualifiedName
        if (qualified != null && qualified.endsWith(".$textual")) return qualified.substringBeforeLast('.') + "." + textual
        val module = klass.containingFile as? PyFile
        if (module != null && module.topLevelClasses.any { it.name == textual }) {
            val moduleQualifiedName = moduleQualifiedName(module) ?: return null
            return "$moduleQualifiedName.$textual"
        }
        return null
    }

    private fun signature(function: PyFunction): SageApiSignature? = SageApiSignature(
        parameters = function.parameterList.parameters.mapNotNull { parameter ->
            val named = parameter as? com.jetbrains.python.psi.PyNamedParameter ?: return@mapNotNull null
            SageApiParameter(
                name = parameter.name ?: "_",
                variadic = named.isPositionalContainer || named.isKeywordContainer,
                keywordOnly = named.isKeywordContainer,
            )
        },
        returnType = returnTypeOf(function),
    )

    private fun returnTypeOf(function: PyFunction): SageTypeRef {
        val annotation = function.annotation?.value?.text?.trim()
        if (!annotation.isNullOrBlank()) return SageTypeRef.known(annotation)
        return SageTypeRef()
    }

    /** The docstring literal carries its quotes; strip them for the summary. */
    private fun documentation(docStringExpression: com.jetbrains.python.psi.PyStringLiteralExpression?, shortName: String): SageApiDocumentation? {
        val literal = docStringExpression ?: return null
        val raw = literal.text.trim()
        val body = raw
            .removePrefix("\"\"\"").removeSuffix("\"\"\"")
            .removePrefix("'''").removeSuffix("'''")
            .trim()
        if (body.isBlank()) return null
        return SageApiDocumentation(summary = body.take(4000), body = null, examples = emptyList())
    }

    private fun isPropertyDecorator(function: PyFunction): Boolean =
        function.decoratorList?.decorators.orEmpty().any { it.text.trim() == "property" || it.text.trim() == "cached_method" }
}
