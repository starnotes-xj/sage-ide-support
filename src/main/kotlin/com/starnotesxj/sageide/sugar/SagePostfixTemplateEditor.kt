package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.settings.PostfixTemplateEditorBase
import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider
import com.intellij.ide.util.gotoByName.ChooseByNameItemProvider
import com.intellij.ide.util.gotoByName.ChooseByNameModel
import com.intellij.ide.util.gotoByName.ChooseByNamePopup
import com.intellij.ide.util.gotoByName.ChooseByNamePopupComponent
import com.intellij.ide.util.gotoByName.DefaultChooseByNameItemProvider
import com.intellij.ide.util.gotoByName.GotoClassModel2
import com.intellij.navigation.ChooseByNameContributor
import com.intellij.navigation.NavigationItem
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.application.ModalityState
import com.intellij.openapi.project.DumbAwareAction
import com.intellij.openapi.project.Project
import com.intellij.openapi.project.ProjectManager
import com.intellij.openapi.ui.Messages
import com.intellij.psi.search.GlobalSearchScope
import com.intellij.util.Processor
import com.intellij.util.indexing.FindSymbolParameters
import com.intellij.util.indexing.IdFilter
import com.jetbrains.python.PyBundle
import com.jetbrains.python.PyGotoClassContributor
import com.jetbrains.python.codeInsight.postfix.PyPostfixTemplateExpressionCondition
import com.jetbrains.python.codeInsight.postfix.PyPostfixTemplateExpressionCondition.PyClassCondition.Companion.create
import com.jetbrains.python.psi.PyClass
import javax.swing.JComponent

/**
 * New-template editor for the Sage postfix provider.
 *
 * Mirrors PyCharm's `PyPostfixTemplateEditor` (which is hard-wired to
 * `PyPostfixTemplateProvider` and therefore not reusable): the same
 * live-template body editor plus expression-type conditions — a Sage-apt
 * selection (generic expression kinds that apply to Python-family PSI plus
 * ready-made sage.all class conditions and a class chooser) — producing
 * [SageEditablePostfixTemplate]s.  The generic
 * [PostfixTemplateEditorBase] accepts any provider, so only the condition
 * list and the factory method are custom.
 */
class SagePostfixTemplateEditor(provider: PostfixTemplateProvider) :
    PostfixTemplateEditorBase<PyPostfixTemplateExpressionCondition?>(provider, true) {

    override fun fillConditions(group: DefaultActionGroup) {
        // Expression-kind conditions (PSI/type based — equally valid for Sage,
        // whose files are Python PSI): the subset that matters for the Sage
        // template family, without Python-only options (boolean/exception).
        group.add(AddConditionAction(PyPostfixTemplateExpressionCondition.PyNumberExpression()))
        group.add(AddConditionAction(PyPostfixTemplateExpressionCondition.PyStringExpression()))
        group.add(AddConditionAction(PyPostfixTemplateExpressionCondition.PyIterable()))
        group.add(AddConditionAction(PyPostfixTemplateExpressionCondition.PyDict()))
        group.add(AddConditionAction(PyPostfixTemplateExpressionCondition.PyList()))
        group.add(AddConditionAction(PyPostfixTemplateExpressionCondition.PySet()))
        group.add(AddConditionAction(PyPostfixTemplateExpressionCondition.PyTuple()))
        group.add(AddConditionAction(PyPostfixTemplateExpressionCondition.PyNonNoneExpression()))
        // Sage-specific: ready-made class conditions for the common sage.all
        // types (resolved through the stub index — the same index that types
        // F.<a> generator statements).
        for (sageType in SAGE_TYPES) {
            val condition = PyPostfixTemplateExpressionCondition.PyClassCondition.create(sageType)
            if (condition != null) {
                group.add(AddConditionAction(condition))
            }
        }
        val projects = ProjectManager.getInstance().openProjects
        if (projects.isNotEmpty()) {
            group.add(ChooseClassAction(projects))
        }
        group.add(EnterClassAction())
    }

    override fun createTemplate(templateId: String, templateName: String): SageEditablePostfixTemplate {
        val templateText = myTemplateEditor.document.text
        // Same as EditablePostfixTemplateWithMultipleExpressions.createTemplate:
        // a TemplateImpl keyed with a placeholder — the key is re-derived on save.
        val liveTemplate = com.intellij.codeInsight.template.impl.TemplateImpl("fakeKey", templateText, "")
        val conditions = LinkedHashSet(myExpressionTypesListModel.elements().toList())
        val useTopmostExpression = myApplyToTheTopmostJBCheckBox.isSelected
        return SageEditablePostfixTemplate(
            templateId, templateName, liveTemplate, "", conditions, useTopmostExpression, myProvider, false,
        )
    }

    override fun getComponent(): JComponent = myEditTemplateAndConditionsPanel

    private inner class ChooseClassAction(private val projects: Array<Project>) : DumbAwareAction(
        PyBundle.messagePointer("settings.postfix.choose.class.action.name")) {
        override fun actionPerformed(e: AnActionEvent) {
            val project = e.project ?: return
            val contributor = MultiProjectPyClassesContributor(projects)
            val model: GotoClassModel2 = object : GotoClassModel2(project) {
                override fun getPromptText(): String {
                    return PyBundle.message("settings.postfix.choose.class.prompt.text")
                }

                override fun getContributorList(): List<ChooseByNameContributor> {
                    return listOf<ChooseByNameContributor>(contributor)
                }

                override fun getCheckBoxName(): String? {
                    return null // don't show checkbox, always search in libraries
                }
            }
            val popup = createPopup(project, model)
            popup.invoke(object : ChooseByNamePopupComponent.Callback() {
                override fun elementChosen(element: Any) {}
                override fun onClose() {
                    if (!popup.closedCorrectly) {
                        return
                    }
                    val chosenElement = popup.chosenElement
                    if (chosenElement is PyClass) {
                        val condition = create(chosenElement)
                        if (condition != null) {
                            myExpressionTypesListModel.addElement(condition)
                        }
                    }
                }
            }, ModalityState.current(), false)
        }
    }

    private class MultiProjectPyClassesContributor(private val projects: Array<Project>) : PyGotoClassContributor() {
        override fun processNames(processor: Processor<in String>, scope: GlobalSearchScope, filter: IdFilter?) {
            for (project in projects) {
                super.processNames(processor, FindSymbolParameters.searchScopeFor(project, true), null)
            }
        }

        override fun processElementsWithName(name: String,
                                             processor: Processor<in NavigationItem?>,
                                             parameters: FindSymbolParameters) {
            for (project in projects) {
                val params = FindSymbolParameters(
                    parameters.completePattern, parameters.localPatternName, FindSymbolParameters.searchScopeFor(project, true))
                super.processElementsWithName(name, processor, params)
            }
        }
    }

    private class ChooseClassByNamePopup(project: Project?,
                                         model: ChooseByNameModel,
                                         provider: ChooseByNameItemProvider,
                                         oldPopup: ChooseByNamePopup?) : ChooseByNamePopup(project, model, provider, oldPopup, null, false,
                                                                                            0) {
        var closedCorrectly = false
        override fun close(isOk: Boolean) {
            if (!checkDisposed()) {
                closedCorrectly = isOk
            }
            super.close(isOk)
        }
    }

    private inner class EnterClassAction : DumbAwareAction(
        PyBundle.messagePointer("settings.postfix.enter.class.action.name")) {
        override fun actionPerformed(e: AnActionEvent) {
            val name = Messages.showInputDialog(myEditTemplateAndConditionsPanel,
                                                PyBundle.message("settings.postfix.enter.fully.qualified.class.name"),
                                                PyBundle.message("settings.postfix.enter.class.dialog.name"), null)
            if (name != null) {
                val condition = create(name)
                if (condition != null) {
                    myExpressionTypesListModel.addElement(condition)
                }
            }
        }
    }

    companion object {
        // Common sage.all types a template author may want to constrain the
        // expression to (qualified names as in the sage stubs; matched by
        // inheritance, so subclasses qualify too).
        private val SAGE_TYPES = listOf(
            "sage.rings.integer.Integer",
            "sage.rings.rational.Rational",
            "sage.rings.real_mpfr.RealNumber",
            "sage.rings.complex_mpfr.ComplexNumber",
            "sage.rings.finite_rings.element_base.FinitePolyExtElement",
            "sage.rings.polynomial.polynomial_element.Polynomial",
            "sage.matrix.matrix0.Matrix",
            "sage.modules.free_module_element.FreeModuleElement",
        )

        private fun createPopup(project: Project?, model: GotoClassModel2): ChooseClassByNamePopup {
            val provider: ChooseByNameItemProvider = DefaultChooseByNameItemProvider(null)
            val oldPopup = project?.getUserData(ChooseByNamePopup.CHOOSE_BY_NAME_POPUP_IN_PROJECT_KEY)
            oldPopup?.close(false)
            val popup = ChooseClassByNamePopup(project, model, provider, oldPopup)
            project?.putUserData(ChooseByNamePopup.CHOOSE_BY_NAME_POPUP_IN_PROJECT_KEY, popup)
            popup.isSearchInAnyPlace = true
            return popup
        }
    }
}
