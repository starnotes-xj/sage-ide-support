package com.starnotesxj.sageide.sugar

import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiInvalidElementAccessException
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
 *
 * Elements handed out by the index must never be dereferenced through their
 * AST node without a validity guard: PyCharm 2026.2 drops PSI ASTs more
 * eagerly (impatient-reader highlighting), so a stale index element can be
 * left with a dangling node reference and `containingFile` throws
 * [PsiInvalidElementAccessException] then.  All reads go through
 * [safeContainingFile] / [safeContainingFilePath], and cached elements are
 * re-validated on every hit.
 */
object SageStubIndex {

    private val positiveCache = java.util.concurrent.ConcurrentHashMap<String, PsiElement>()

    fun findDeclaration(project: Project, name: String): PsiElement? {
        positiveCache[name]?.let {
            if (it.isValid) return it
            positiveCache.remove(name)
        }
        val candidates = mutableListOf<PsiElement>()
        PyFunctionNameIndex.find(name, project, GlobalSearchScope.allScope(project)).forEach { candidates += it }
        PyClassNameIndex.find(name, project, GlobalSearchScope.allScope(project)).forEach { candidates += it }
        val result = candidates.firstOrNull { isSageStubDeclaration(it) }
        if (result != null) {
            positiveCache[name] = result
            LOG.warn("Sage stub index hit: '$name' -> ${safeContainingFilePath(result)}")
        } else if (candidates.isNotEmpty()) {
            // Candidates exist but the path filter rejected them all — worth a
            // warn.  Zero candidates is the normal case for user identifiers.
            LOG.warn(
                "Sage stub index miss for '$name' (candidates: ${candidates.size}, " +
                    "first: ${safeContainingFilePath(candidates.first())})",
            )
        }
        return result
    }

    private fun isSageStubDeclaration(element: PsiElement): Boolean =
        isSageStubFile(safeContainingFile(element))

    /** True for `.pyi` files inside the installed Sage stub tree (`site-packages/sage`). */
    @JvmStatic
    fun isSageStubFile(file: PsiFile?): Boolean {
        val path = file?.virtualFile?.path ?: return false
        if (!file.name.endsWith(".pyi") || !path.endsWith(".pyi")) return false
        // Match the `site-packages/sage/...` path segment EXACTLY.  A loose
        // `path.contains("sage")` also matches a conda env named `envs/sage`
        // (the user's real layout!), which would admit every .pyi under that
        // env's site-packages — e.g. builtins.pyi — as a "sage stub".
        return path.contains("/site-packages/sage/") || path.contains("\\site-packages\\sage\\")
    }

    /**
     * Finds a class declaration by its simple name in the installed Sage stub tree.
     * Positive results are cached per name (same policy as [findDeclaration]).
     */
    fun findClass(project: Project, name: String): PyClass? {
        classCache[name]?.let {
            if (it.isValid) return it
            classCache.remove(name)
        }
        val candidates = PyClassNameIndex.find(name, project, GlobalSearchScope.allScope(project))
        val result = candidates.firstOrNull { isSageStubFile(safeContainingFile(it)) }
        if (result != null) {
            classCache[name] = result
            LOG.warn("Sage stub class index hit: '$name' -> ${safeContainingFilePath(result)}")
        } else {
            LOG.warn("Sage stub class index miss for '$name' (candidates: ${candidates.size})")
        }
        return result
    }

    private fun safeContainingFile(element: PsiElement): PsiFile? {
        if (!element.isValid) return null
        return try {
            element.containingFile
        } catch (_: PsiInvalidElementAccessException) {
            null
        }
    }

    private fun safeContainingFilePath(element: PsiElement): String =
        safeContainingFile(element)?.virtualFile?.path ?: "<invalid>"

    private val classCache = java.util.concurrent.ConcurrentHashMap<String, PyClass>()

    private val LOG = Logger.getInstance(SageStubIndex::class.java)
}
