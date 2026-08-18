package com.starnotesxj.sageide.sugar

import com.intellij.openapi.diagnostic.Logger
import com.intellij.openapi.project.Project
import com.intellij.psi.PsiElement
import com.intellij.psi.PsiFile
import com.intellij.psi.PsiInvalidElementAccessException
import com.intellij.psi.search.GlobalSearchScope
import com.jetbrains.python.psi.PyClass
import com.jetbrains.python.psi.PyFile
import com.jetbrains.python.psi.PyFromImportStatement
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyImportElement
import com.jetbrains.python.psi.PyListLiteralExpression
import com.jetbrains.python.psi.PyStringLiteralExpression
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.resolve.QualifiedNameFinder
import com.jetbrains.python.psi.stubs.PyClassNameIndex
import com.jetbrains.python.psi.stubs.PyFunctionNameIndex
import com.jetbrains.python.psi.types.PyCallableType
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyOverloadType
import com.jetbrains.python.psi.types.PyType
import com.jetbrains.python.psi.types.TypeEvalContext

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
     * (`from sage.interfaces.ecm import ECM as ECM` — most of all.pyi is such
     * re-export aliases), followed to the REAL declaration so PyCharm's type
     * engine can type the result.  Returning the target restores the type
     * chain: `ZZ` -> the integer-ring type, `N` -> the `numerical_approx`
     * callable signature, `ECM` -> the ECM class (so `ecm = ECM()` types and
     * `ecm.` completes `factor`).
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
                    // Follow the alias to the REAL declaration.  The import
                    // element itself is invisible to PyCharm's type engine:
                    // `PyReferenceExpressionImpl.getTypeFromTarget` can only
                    // type PyFunction/PyClass/PyTypedElement targets, so an
                    // alias like `from sage.interfaces.ecm import ECM as ECM`
                    // returned as-is leaves `ECM()` untyped and kills every
                    // downstream member completion (`ecm.factor` etc.) —
                    // v1.7.6 bug.  See [followImportAlias] for why the
                    // import element's own reference is not used.
                    val importedName = importElement.importedQName?.lastComponent ?: name
                    val moduleQName = fromImport.importSource?.asQualifiedName()?.toString()
                    val target = followImportAlias(project, moduleQName, importedName)
                    if (target != null && target.isValid) {
                        LOG.warn("Sage stub sage.all import-alias hit: '$name' -> ${safeContainingFilePath(target)}")
                        return target
                    }
                    LOG.warn("Sage stub sage.all import-alias hit: '$name' in ${safeContainingFilePath(importElement)}")
                    return importElement
                }
            }
        }
        // No warn on a miss: user identifiers legitimately miss every path
        // and would flood the log.
        return null
    }

    /**
     * Follows a `from <module> import <name>` alias of the generated all.pyi
     * to the REAL declaration (class/function/attribute) via the name
     * indexes: exact module match first (`sage.interfaces.ecm.ECM`), then any
     * declaration in the sage stub tree, then null.
     *
     * The import element's own `PyImportReference` is deliberately NOT used:
     * resolving it from inside the all.pyi stub tree returned null for every
     * alias in the wild (idea.log 2026-08-18 showed only the fallback branch
     * of the caller), while the function/class indexes are exactly the data
     * source the rest of this file already relies on.
     */
    private fun followImportAlias(project: Project, moduleQName: String?, importedName: String): PsiElement? {
        val candidates = ArrayList<PsiElement>()
        PyFunctionNameIndex.find(importedName, project, GlobalSearchScope.allScope(project))
            .forEach { candidates += it }
        PyClassNameIndex.find(importedName, project, GlobalSearchScope.allScope(project))
            .forEach { candidates += it }
        return candidates.firstOrNull { candidate ->
            val file = safeContainingFile(candidate) ?: return@firstOrNull false
            moduleQName != null &&
                QualifiedNameFinder.findShortestImportableQName(file)?.toString() == moduleQName
        } ?: candidates.firstOrNull { isSageStubFile(safeContainingFile(it)) }
    }

    /**
     * Whether a sage.all name is callable, so the implicit-namespace
     * completion can append `()` like PyCharm does for plain functions.
     * PyFunction/PyClass are callable; a PyTargetExpression instance is
     * callable when its class has `__call__` (ZZ/QQ/RR/CC/SR and the symbolic
     * function wrappers do; pi/e/true/false/NaN do not); a from-import alias
     * is followed to its real declaration first ([followImportAlias]).
     * Results are cached per name.
     */
    fun isCallableDeclaration(project: Project, name: String, element: PsiElement?): Boolean {
        callableCache[name]?.let { return it }
        val result = computeIsCallable(project, name, element)
        callableCache[name] = result
        return result
    }

    private fun computeIsCallable(project: Project, name: String, element: PsiElement?): Boolean {
        val target: PsiElement? = when (element) {
            is PyFunction, is PyClass -> element
            is PyImportElement -> {
                val statement = element.containingImportStatement as? PyFromImportStatement
                val moduleQName = statement?.importSource?.asQualifiedName()?.toString()
                val importedName = element.importedQName?.lastComponent ?: name
                followImportAlias(project, moduleQName, importedName)
            }
            is PyTargetExpression -> element
            else -> return false
        }
        return when (target) {
            is PyFunction, is PyClass -> true
            is PyTargetExpression -> {
                val type = try {
                    TypeEvalContext.codeCompletion(project, target.containingFile).getType(target)
                } catch (_: RuntimeException) {
                    null
                }
                isCallableValueType(type)
            }
            else -> false
        }
    }

    private fun isCallableValueType(type: PyType?): Boolean = when (type) {
        null -> false
        // For an INSTANCE of a class, callable iff the class defines
        // `__call__` (PyClassTypeImpl.isCallable -> PyABCUtil -> hasMethod).
        // A PyClassType is a PyCallableType by hierarchy, so this branch must
        // come first to get the __call__-based answer.
        is PyClassType -> type.isCallable
        is PyOverloadType -> true
        is PyCallableType -> true
        else -> false
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
     * All names of the runtime-injected `sage.all` namespace, mapped to a
     * representative declaration element in the generated `sage/all.pyi`
     * (the element is null for names that have no per-name declaration in the
     * stub file — e.g. aliases synthesized by the real all.py at runtime —
     * but the name itself is still a valid namespace member).
     *
     * Source of truth is the stub's `__all__` list (the exact namespace the
     * `sage` command injects); top-level functions/classes/attributes and
     * from-import aliases are unioned in for robustness.  The result is
     * cached for the session: the installed stubs only change when the user
     * regenerates them, and the cache entries are re-validated on every use
     * (same policy as [findDeclaration]).
     */
    fun collectSageAllDeclarations(project: Project): Map<String, PsiElement?> {
        sageAllDeclarationsCache?.let { return it }
        return synchronized(this) {
            sageAllDeclarationsCache ?: computeSageAllDeclarations(project).also {
                // Negative results are NOT cached (same policy as
                // findDeclaration): the first completion can happen before the
                // SDK stubs are indexed, and caching that miss would poison
                // every later completion.
                if (it.isNotEmpty()) sageAllDeclarationsCache = it
            }
        }
    }

    private fun computeSageAllDeclarations(project: Project): Map<String, PsiElement?> {
        val allFile = sageAllFile(project)
            ?: run {
                LOG.warn("Sage stub sage.all anchor '$SAGE_ALL_ANCHOR_NAME' not found — cannot enumerate sage.all names")
                return emptyMap()
            }
        val byName = LinkedHashMap<String, PsiElement?>()

        // 1. Top-level attributes: ZZ/QQ/RR/CC/SR and the other module-level
        //    instances (`RR: _Type_RR` in the generated all.pyi).
        for (attribute in allFile.topLevelAttributes) {
            val name = attribute.name ?: continue
            if (name == "__all__") continue
            byName.putIfAbsent(name, attribute)
        }
        // 2. Top-level functions: GF, Mod, factor, ... (`def GF(...)` etc.).
        for (function in allFile.topLevelFunctions) {
            val name = function.name ?: continue
            byName.putIfAbsent(name, function)
        }
        // 3. Top-level classes.
        for (pyClass in allFile.topLevelClasses) {
            val name = pyClass.name ?: continue
            byName.putIfAbsent(name, pyClass)
        }
        // 4. From-import aliases: `from sage.misc.functional import
        //    numerical_approx as N` — N is invisible to the other collections.
        for (fromImport in allFile.fromImports) {
            for (importElement in fromImport.importElements) {
                val name = importElement.visibleName ?: continue
                byName.putIfAbsent(name, importElement)
            }
        }
        // 5. The authoritative namespace: the `__all__` list at the end of
        //    the generated all.pyi.  Names listed there but declared nowhere
        //    (runtime-synthesized aliases) are added without an element.
        for (entry in (allFile.findTopLevelAttribute("__all__")
                ?.findAssignedValue() as? PyListLiteralExpression)?.elements.orEmpty()) {
            val name = (entry as? PyStringLiteralExpression)?.stringValue ?: continue
            byName.putIfAbsent(name, byName[name])
        }
        return byName
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

    /** Session cache of the sage.all namespace: name -> declaration in `sage/all.pyi` (null when undeclared). */
    @Volatile
    private var sageAllDeclarationsCache: Map<String, PsiElement?>? = null

    /** Session cache of callability per sage.all name (see [isCallableDeclaration]). */
    private val callableCache = java.util.concurrent.ConcurrentHashMap<String, Boolean>()

    private val LOG = Logger.getInstance(SageStubIndex::class.java)
}
