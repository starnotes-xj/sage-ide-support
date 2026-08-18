package com.starnotesxj.sageide.type

import com.intellij.openapi.util.Key
import com.intellij.openapi.util.RecursionManager
import com.intellij.openapi.util.Ref
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.PyCallableType
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyClassTypeImpl
import com.jetbrains.python.psi.types.PyTupleType
import com.jetbrains.python.psi.types.PyType
import com.jetbrains.python.psi.types.PyTypeProviderBase
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer
import com.starnotesxj.sageide.sugar.SageSugarInfo

/**
 * Types the targets of Sage preparse-sugar statements.
 *
 * `F.<a> = GF(2^8, ...)` is built by [com.jetbrains.python.parsing.SageParser]
 * as a real multi-target assignment, and this provider gives:
 *
 * - the factory target `F` the return type of the constructor call `GF(...)`,
 *   resolved through the installed sage stubs (so `F.` completion works);
 * - each generator target (`a`) the element type of `F._first_ngens(...)`.
 *
 * The right-hand side references the generator targets (e.g. `modulus=x^8 + ...`
 * uses `x`), so `context.getType(call)` can re-enter this provider; the recursion
 * guard and the per-statement cache break the cycle.
 *
 * NOTE (v1.3.0): the return-type patches for unannotated sage stub methods
 * (`from_integer` and friends) were REMOVED — the stubgen curated table now
 * annotates them directly (`FiniteField_givaroElement | ...`), so the type
 * knowledge lives in the stubs, not in the IDE.  Registered `order="first"`
 * because the type-provider EP loops stop at the first non-null Ref (even a
 * null-content one), and this provider answers only for sugar targets in
 * `.sage` files.
 */
class SageTypeProvider : PyTypeProviderBase() {

    override fun getReferenceType(
        referenceTarget: PsiElement,
        context: TypeEvalContext,
        anchor: PsiElement?,
    ): Ref<PyType>? {
        val target = referenceTarget as? PyTargetExpression ?: return null
        // Factory attributes in the generated sage/all.pyi whose `_Type_*`
        // annotation alias dangles: `CC: _Type_CC` imports
        // `ComplexField_class_with_category`, a RUNTIME-ONLY subclass name —
        // the stubs only declare `ComplexField_class`, so the annotation
        // fails to resolve and `CC` loses both its type (`CC()` untyped) and
        // its __call__-based callability (no parens in completion).  Follow
        // the alias (with the `_with_category` fallback) to the real class
        // and return its INSTANCE type.  Only answers inside the sage stub
        // tree; everywhere else the sugar handling below applies or null is
        // returned.
        if (SageStubIndex.isSageStubFile(target.containingFile)) {
            val type = sageAllFactoryAttributeType(target) ?: return null
            return Ref.create(type)
        }
        if (!SageFileUtils.isSageFile(target.containingFile)) return null
        val statement = PsiTreeUtil.getParentOfType(target, PyAssignmentStatement::class.java) ?: return null

        return RecursionManager.doPreventingRecursion(target, true) {
            val info = SageSugarAnalyzer.analyze(statement) ?: return@doPreventingRecursion null
            val factoryType = factoryType(statement, info, context)
            LOG.warn(
                "Sage: sugar target '${target.name}' factoryTarget='${info.factoryTarget.name}' " +
                    "factoryType=${factoryType?.renderTypeName() ?: "null"} call=${info.call?.text?.take(60)}",
            )
            if (factoryType == null) return@doPreventingRecursion null

            val type: PyType? = when {
                target === info.factoryTarget -> factoryType
                target in info.nameTargets -> generatorType(factoryType, context)
                else -> null
            }
            type?.let { Ref.create(it) }
        }
    }

    private fun PyType.renderTypeName(): String =
        (this as? PyClassType)?.name ?: this.javaClass.simpleName

    private fun factoryType(
        statement: PyAssignmentStatement,
        info: SageSugarInfo,
        context: TypeEvalContext,
    ): PyType? {
        statement.getUserData(FACTORY_TYPE_KEY)?.let { return it }
        val call = info.call ?: return null
        val type = context.getType(call) ?: return null
        statement.putUserData(FACTORY_TYPE_KEY, type)
        return type
    }

    /** `(a,) = F._first_ngens(1)` — the generator type is the element type of the tuple. */
    private fun generatorType(factoryType: PyType, context: TypeEvalContext): PyType? {
        val pyClass = (factoryType as? PyClassType)?.pyClass?.takeIf { it.isValid } ?: return null
        val firstNgens = pyClass.findMethodByName("_first_ngens", true, context) ?: return null
        val callable = context.getType(firstNgens) as? PyCallableType ?: return null
        val returnType = callable.getReturnType(context) ?: return null
        return (returnType as? PyTupleType)?.getElementType(0) ?: returnType
    }

    /**
     * The instance type of a `Name: _Type_Name` factory attribute in the
     * generated `sage/all.pyi`, resolved by following the `_Type_Name`
     * from-import alias to the real class (with the `_with_category`
     * fallback).  Null for anything that is not such an attribute or whose
     * alias cannot be followed.
     */
    private fun sageAllFactoryAttributeType(target: PyTargetExpression): PyType? {
        val file = target.containingFile as? com.jetbrains.python.psi.PyFile ?: return null
        val annotation = target.annotationValue as? com.jetbrains.python.psi.PyReferenceExpression ?: return null
        val aliasName = annotation.referencedName ?: return null
        if (!aliasName.startsWith("_Type_")) return null
        for (fromImport in file.fromImports) {
            for (importElement in fromImport.importElements) {
                if (importElement.visibleName != aliasName) continue
                val moduleQName = fromImport.importSource?.asQualifiedName()?.toString()
                val importedName = importElement.importedQName?.lastComponent ?: aliasName
                val cls = SageStubIndex.findAliasClass(target.project, moduleQName, importedName)
                    ?: continue
                if (!cls.isValid) continue
                LOG.warn("Sage: factory attribute '${target.name}' typed as instance of ${cls.name}")
                return PyClassTypeImpl(cls, false)
            }
        }
        return null
    }

    companion object {
        private val FACTORY_TYPE_KEY = Key.create<PyType>("sageide.sugar.factoryType")
        private val LOG = com.intellij.openapi.diagnostic.Logger.getInstance(SageTypeProvider::class.java)
    }
}
