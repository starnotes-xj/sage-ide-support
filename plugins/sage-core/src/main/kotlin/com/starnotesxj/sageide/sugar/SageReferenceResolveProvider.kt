package com.starnotesxj.sageide.sugar

import com.intellij.openapi.diagnostic.Logger
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyQualifiedExpression
import com.jetbrains.python.psi.PyReferenceExpression
import com.jetbrains.python.psi.impl.ResolveResultList
import com.jetbrains.python.psi.resolve.PyReferenceResolveProvider
import com.jetbrains.python.psi.resolve.RatedResolveResult
import com.jetbrains.python.psi.types.TypeEvalContext

/**
 * Makes the runtime-injected `sage.all` namespace visible to static analysis
 * in `.sage` files.
 *
 * The `sage` command executes `.sage` files with the whole `sage.all`
 * namespace injected at runtime, but PyCharm's Python resolver knows nothing
 * about that injection: `GF`, `Integer`, ... are unresolved without an
 * explicit import.
 *
 * This provider is consulted by [com.jetbrains.python.psi.impl.references.PyReferenceImpl]
 * whenever ordinary Python resolution fails, and resolves the name to its
 * declaration in the installed Sage stub tree.  It is the same mechanism that
 * resolves builtins (`PythonBuiltinReferenceResolveProvider`) and IPython
 * magics (`PyIPythonBuiltinReferenceResolveProvider`).
 *
 * WHY NOT A PsiReferenceContributor: `PyReferenceExpression.getReference()`
 * returns a single primary reference (`PyReferenceImpl` / `PyQualifiedReference`)
 * that never consults `PsiReferenceService`, and both the unresolved-reference
 * inspection (`PyUnresolvedReferencesVisitor.visitPyElement` -> `getReference`)
 * and type inference (`PyReferenceExpressionImpl.getType` -> `multiResolveTopPriority(getReference)`)
 * use exactly that primary reference.  Contributor-supplied references are
 * therefore invisible to the inspection and to type inference — which is why
 * `GF` stayed red and `e.` stayed untyped despite the contributor resolving.
 * (Observed: no "Sage stub" warn logs at all, because nothing called
 * `getReferences()` during a plain open/type round trip.)
 *
 * Also resolves generator names used inside their own sugar statement's RHS
 * (e.g. `x` in `F.<a> = GF(2^8, modulus=x^8 + ...)`) to the generator target.
 */
class SageReferenceResolveProvider : PyReferenceResolveProvider {

    override fun resolveName(element: PyQualifiedExpression, context: TypeEvalContext): List<RatedResolveResult> {
        val reference = element as? PyReferenceExpression ?: return emptyList()
        if (reference.isQualified) return emptyList()
        val file = reference.containingFile ?: return emptyList()
        if (!SageFileUtils.isSageFile(file)) return emptyList()
        val name = reference.referencedName ?: return emptyList()

        // Files with an explicit sage.all import are handled by the default
        // resolver.  The check must be PSI-based, not a text scan: a
        // COMMENTED-OUT import (`# from sage.all import *`) leaves no
        // statement in the parse tree and must NOT disable the implicit
        // namespace — the `sage` command injects sage.all regardless, so
        // running works while a text-scan gate would leave GF/ZZ unresolved.
        if (SageFileUtils.hasExplicitSageAllImport(file)) return emptyList()

        // 1. Generator targets of the enclosing sugar statement (RHS-internal uses).
        val statement = PsiTreeUtil.getParentOfType(reference, PyAssignmentStatement::class.java)
        if (statement != null) {
            val info = SageSugarAnalyzer.analyze(statement)
            if (info != null) {
                val target = info.nameTargets.firstOrNull { it.name == name }
                if (target != null) return ResolveResultList.to(target)
            }
        }

        // 2. The implicit sage.all namespace via the stub index.
        val declaration = SageStubIndex.findDeclaration(reference.project, name) ?: return emptyList()
        // The index element's AST may already be dropped (PyCharm 2026.2
        // impatient-reader highlighting); never hand an invalid element back.
        if (!declaration.isValid) return emptyList()
        LOG.warn("Sage: resolved implicit name '$name'")
        return ResolveResultList.to(declaration)
    }

    companion object {
        private val LOG = Logger.getInstance(SageReferenceResolveProvider::class.java)
    }
}
