package com.starnotesxj.sageide.sugar

import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiInvalidElementAccessException
import com.intellij.psi.search.GlobalSearchScope
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.PyTargetExpression
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
        // 1. The sage.all module is the namespace the `sage` command actually
        //    injects — its declarations MUST win over the global name indexes:
        //    single-letter names (N, n) collide with unrelated sage modules
        //    (e.g. `modular/modsym/p1list.pyi`'s N), and resolving them there
        //    yields a wrong signature ("unexpected argument" on N(1)).
        findSageAllDeclaration(project, name)?.let {
            positiveCache[name] = it
            return it
        }
        // 2. Global function/class index fallback (GF and other sage.all
        //    functions declared as `def` in all.pyi).  Prefer candidates
        //    declared in all.pyi itself, then any sage stub file.
        val candidates = mutableListOf<PsiElement>()
        PyFunctionNameIndex.find(name, project, GlobalSearchScope.allScope(project)).forEach { candidates += it }
        PyClassNameIndex.find(name, project, GlobalSearchScope.allScope(project)).forEach { candidates += it }
        val result = candidates.firstOrNull { isSageAllFile(safeContainingFile(it)) }
            ?: candidates.firstOrNull { isSageStubDeclaration(it) }
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

    /**
     * Resolves a name inside the `sage.all` stub module: first a top-level
     * attribute (`ZZ: _Type_ZZ` — module-level instances that neither the
     * function nor the class index covers), then a from-import alias
     * (`from sage.misc.functional import numerical_approx as N` — `N` is an
     * import target, also invisible to both indexes).  Returning the target
     * restores the type chain: `ZZ` -> the integer-ring type, `N` -> the
     * `numerical_approx` callable signature.
     *
     * The `sage.all` stub module is located through the function index on a
     * name that provably resolves there ([SAGE_ALL_ANCHOR_NAME] — `GF` is a
     * `def` in the generated all.pyi and the same index path that resolves
     * GF for the user): PyModuleNameIndex does not reliably index `.pyi`
     * stub modules, so locating the file through it failed in the wild.
     */
    private fun findSageAllDeclaration(project: Project, name: String): PsiElement? {
        val allFile = sageAllFile(project)
        if (allFile == null) {
            LOG.warn("Sage stub sage.all anchor '$SAGE_ALL_ANCHOR_NAME' not found — cannot resolve '$name'")
            return null
        }
        allFile.findTopLevelAttribute(name)?.let { attribute ->
            if (attribute.isValid) {
                LOG.warn("Sage stub sage.all attribute hit: '$name' in ${safeContainingFilePath(attribute)}")
                return attribute
            }
        }
        for (fromImport in allFile.fromImports) {
            for (importElement in fromImport.importElements) {
                if (importElement.visibleName == name) {
                    if (!importElement.isValid) return null
                    LOG.warn("Sage stub sage.all import-alias hit: '$name' in ${safeContainingFilePath(importElement)}")
                    return importElement
                }
            }
        }
        // No warn on a miss: user identifiers legitimately miss every path
        // and would flood the log.
        return null
    }

    /** The `sage/all.pyi` stub module, located through the GF function-index anchor. */
    private fun sageAllFile(project: Project): PyFile? {
        val anchor = PyFunctionNameIndex.find(SAGE_ALL_ANCHOR_NAME, project, GlobalSearchScope.allScope(project))
            .firstOrNull { isSageStubDeclaration(it) }
        return anchor?.let { safeContainingFile(it) } as? PyFile
    }

    private fun isSageAllFile(file: PsiFile?): Boolean = isSageStubFile(file) && file?.name == "all.pyi"

    /** A name that the generated `sage/all.pyi` declares as a `def`, used to locate the module file. */
    private const val SAGE_ALL_ANCHOR_NAME = "GF"

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
