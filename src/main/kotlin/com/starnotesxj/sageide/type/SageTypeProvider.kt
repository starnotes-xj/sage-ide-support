package com.starnotesxj.sageide.type

import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Key
import com.intellij.openapi.util.RecursionManager
import com.intellij.openapi.util.Ref
import com.intellij.psi.PsiElement
import com.intellij.psi.util.PsiTreeUtil
import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyCallable
import com.jetbrains.python.psi.PyFunction
import com.jetbrains.python.psi.PyTargetExpression
import com.jetbrains.python.psi.types.PyCallableType
import com.jetbrains.python.psi.types.PyClassType
import com.jetbrains.python.psi.types.PyClassTypeImpl
import com.jetbrains.python.psi.types.PyTupleType
import com.jetbrains.python.psi.types.PyType
import com.jetbrains.python.psi.types.PyTypeProviderBase
import com.jetbrains.python.psi.types.PyUnionType
import com.jetbrains.python.psi.types.TypeEvalContext
import com.starnotesxj.sageide.sugar.SageFileUtils
import com.starnotesxj.sageide.sugar.SageStubIndex
import com.starnotesxj.sageide.sugar.SageSugarAnalyzer
import com.starnotesxj.sageide.sugar.SageSugarInfo

/**
 * Types the targets of Sage preparse-sugar statements and patches the return
 * types of sage stub methods whose generated stubs lack an annotation.
 *
 * Sugar statements:
 *
 * `F.<a> = GF(2^8, ...)` parses with error recovery into an assignment whose
 * left-hand side is a comparison expression, so the Python inference never treats
 * `F` as a real assignment target.  This provider recognizes the sugar shape and
 * gives:
 *
 * - the factory target `F` the return type of the constructor call `GF(...)`, resolved
 *   through the installed sage stubs (so `F.` completion works);
 * - each generator target (`a`) the element type of `F._first_ngens(...)`.
 *
 * The right-hand side references the generator targets (e.g. `modulus=x^8 + ...`
 * uses `x`), so `context.getType(call)` can re-enter this provider; the recursion
 * guard and the per-statement cache break the cycle.
 *
 * Missing stub return types:
 *
 * The stubgen-generated stubs annotate return types only where the docstring
 * maps to a known type name ("整数" -> Integer, "多项式" -> Polynomial, ...).
 * The finite-field docstrings say "域元素" (field element), which the stubgen
 * does not map, so `from_integer`, `random_element`, `multiplicative_generator`
 * and friends come out untyped and `e = F.from_integer(0x57)` would be Unknown.
 * This provider supplies the missing types by resolving the concrete finite-field
 * element classes from the stubs themselves:
 *
 * - element-returning methods of finite-field classes -> the union of
 *   FiniteField_givaroElement / FiniteField_ntl_gf2eElement /
 *   FiniteFieldElement_pari_ffelt (each of which carries `to_integer`,
 *   `polynomial`, `log`, `multiplicative_order`);
 * - `multiplicative_order` / `log` of finite-field element classes -> Integer.
 *
 * Both `PyFunctionImpl.getReturnType` and `PyFunctionTypeImpl.getCallType`
 * consult this extension point first (first non-null wins), so a single
 * [getReturnType] override covers direct return-type queries and call typing.
 */
class SageTypeProvider : PyTypeProviderBase() {

    override fun getReferenceType(
        referenceTarget: PsiElement,
        context: TypeEvalContext,
        anchor: PsiElement?,
    ): Ref<PyType>? {
        val target = referenceTarget as? PyTargetExpression ?: return null
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

    override fun getReturnType(callable: PyCallable, context: TypeEvalContext): Ref<PyType>? {
        val function = callable as? PyFunction ?: return null
        // Only patch declarations inside the installed sage stub tree; everything
        // else keeps its own (possibly absent) typing.
        if (!SageStubIndex.isSageStubFile(function.containingFile)) return null
        val className = function.containingClass?.qualifiedName ?: return null
        val methodName = function.name ?: return null

        val type: PyType? = when {
            methodName in ELEMENT_RETURNING_METHODS && className.startsWith("sage.rings.finite_rings.finite_field") ->
                finiteFieldElementType(function.project)
            methodName in INTEGER_RETURNING_METHODS && isFiniteFieldElementClass(className) ->
                sageIntegerType(function.project)
            else -> null
        }
        LOG.warn("Sage: getReturnType $className.$methodName -> ${type?.renderTypeName() ?: "null"}")
        return type?.let { Ref.create(it) }
    }

    private fun PyType.renderTypeName(): String =
        (this as? PyClassType)?.name ?: this.javaClass.simpleName

    /** Union of the concrete finite-field element classes from the stubs. */
    private fun finiteFieldElementType(project: Project): PyType? {
        elementTypeCache[project]?.let { return it }
        val types = ELEMENT_CLASS_NAMES.mapNotNull { SageStubIndex.findClass(project, it) }
            .map { PyClassTypeImpl(it, false) }
        if (types.isEmpty()) return null
        val result: PyType = if (types.size == 1) {
            types.first()
        }
        else {
            PyUnionType.union(types) ?: return null
        }
        elementTypeCache[project] = result
        return result
    }

    private fun sageIntegerType(project: Project): PyType? {
        integerTypeCache[project]?.let { return it }
        val result = SageStubIndex.findClass(project, "Integer")?.let { PyClassTypeImpl(it, false) }
        if (result != null) {
            integerTypeCache[project] = result
        }
        return result
    }

    private fun isFiniteFieldElementClass(className: String): Boolean =
        className.startsWith("sage.rings.finite_rings.element_")

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
        val pyClass = (factoryType as? PyClassType)?.pyClass ?: return null
        val firstNgens = pyClass.findMethodByName("_first_ngens", true, context) ?: return null
        val callable = context.getType(firstNgens) as? PyCallableType ?: return null
        val returnType = callable.getReturnType(context) ?: return null
        return (returnType as? PyTupleType)?.getElementType(0) ?: returnType
    }

    companion object {
        private val FACTORY_TYPE_KEY = Key.create<PyType>("sageide.sugar.factoryType")
        private val LOG = com.intellij.openapi.diagnostic.Logger.getInstance(SageTypeProvider::class.java)

        /** Methods on finite-field classes whose stub docstring says "域元素" but carries no annotation. */
        private val ELEMENT_RETURNING_METHODS = setOf(
            "from_integer", "random_element", "multiplicative_generator",
        )

        /** Methods on finite-field element classes whose stub docstring says "整数" but carries no annotation. */
        private val INTEGER_RETURNING_METHODS = setOf(
            "multiplicative_order", "log",
        )

        private val ELEMENT_CLASS_NAMES = listOf(
            "FiniteField_givaroElement",
            "FiniteField_ntl_gf2eElement",
            "FiniteFieldElement_pari_ffelt",
        )

        /** Positive-only caches: a miss may just mean the SDK is not indexed yet. */
        private val elementTypeCache = java.util.concurrent.ConcurrentHashMap<Project, PyType>()
        private val integerTypeCache = java.util.concurrent.ConcurrentHashMap<Project, PyType>()
    }
}
