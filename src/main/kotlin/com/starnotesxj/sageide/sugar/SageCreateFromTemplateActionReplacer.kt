package com.starnotesxj.sageide.sugar

import com.intellij.ide.fileTemplates.CreateFromTemplateActionReplacer
import com.intellij.ide.fileTemplates.FileTemplate
import com.intellij.ide.fileTemplates.actions.CreateFromTemplateAction
import com.intellij.openapi.actionSystem.AnAction

/**
 * Replaces the default action for our "Sage File" file template everywhere
 * the platform lists file templates as actions (the New → From Template
 * group, recent-templates popup, ...).
 *
 * The default `CreateFromTemplateAction` shows `FileTemplate.getName()` —
 * the resource-file name "Sage File" — which cannot be localized.  This
 * replacer supplies an action whose text is the localized entry
 * ("Sage 文件" on a zh-CN IDE, "Sage File" otherwise); creation still goes
 * through the same template, so the resulting file is identical.
 */
class SageCreateFromTemplateActionReplacer : CreateFromTemplateActionReplacer {

    override fun replaceCreateFromFileTemplateAction(fileTemplate: FileTemplate): AnAction? {
        if (fileTemplate.name != SageFileTemplatesFactory.SAGE_FILE_TEMPLATE) return null
        return CreateFromTemplateAction(SageUiText.sageFileEntry(), SageIcons.SAGE) { fileTemplate }
    }
}
