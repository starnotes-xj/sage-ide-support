package com.starnotesxj.sageide.sugar

import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.search.GlobalSearchScope
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.stubs.PyClassNameIndex
import com.jetbrains.python.psi.stubs.PyFunctionNameIndex

/**
 * Looks up declarations of Sage built-in names in the SDK's generated stubs.
 *
 * `.sage` files get the sage.all namespace injected at runtime by the sage
 * command, but static analysis has no such injection: `GF`, `Integer`, ...
 * appear unresolved without an import.  This index resolves those names to
 * their declaration inside the installed Sage stub tree (`.pyi` files under
 * `site-packages/sage`), restoring the whole type chain.
 *
 * Negative results are NOT cached: the first lookup can happen before the
 * SDK stubs are indexed, and caching that miss would poison every later
 * resolution.  Positive results are cached per name.
 */
object SageStubIndex {

    private val positiveCache = java.util.concurrent.ConcurrentHashMap<String, PsiElement>()

    fun findDeclaration(project: Project, name: String): PsiElement? {
        positiveCache[name]?.let { return it }
        val candidates = mutableListOf<PsiElement>()
        PyFunctionNameIndex.find(name, project, GlobalSearchScope.allScope(project)).forEach { candidates += it }
        PyClassNameIndex.find(name, project, GlobalSearchScope.allScope(project)).forEach { candidates += it }
        val result = candidates.firstOrNull { isSageStubDeclaration(it) }
        if (result != null) {
            positiveCache[name] = result
            LOG.warn("Sage stub index hit: '$name' -> ${result.containingFile?.virtualFile?.path}")
        }
        else {
            LOG.warn("Sage stub index miss for '$name' (candidates: ${candidates.size})")
        }
        return result
    }

    private fun isSageStubDeclaration(element: PsiElement): Boolean =
        isSageStubFile(element.containingFile)

    /** True for `.pyi` files inside the installed Sage stub tree (`site-packages/sage`). */
    @JvmStatic
    fun isSageStubFile(file: PsiFile?): Boolean {
        val path = file?.virtualFile?.path ?: return false
        return file.name.endsWith(".pyi") &&
            path.contains("site-packages") &&
            path.contains("sage") &&
            path.endsWith(".pyi")
    }

    /**
     * Finds a class declaration by its simple name in the installed Sage stub tree.
     * Positive results are cached per name (same policy as [findDeclaration]).
     */
    fun findClass(project: Project, name: String): PyClass? {
        (classCache[name])?.let { return it }
        val result = PyClassNameIndex.find(name, project, GlobalSearchScope.allScope(project))
            .firstOrNull { isSageStubFile(it.containingFile) }
        if (result != null) {
            classCache[name] = result
        }
        return result
    }

    private val classCache = java.util.concurrent.ConcurrentHashMap<String, PyClass>()

    private val LOG = Logger.getInstance(SageStubIndex::class.java)
}

