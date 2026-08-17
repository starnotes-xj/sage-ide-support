package com.starnotesxj.sageide.sugar

import com.intellij.ide.fileTemplates.FileTemplateDescriptor
import com.intellij.ide.fileTemplates.FileTemplateGroupDescriptor
import com.intellij.ide.fileTemplates.FileTemplateGroupDescriptorFactory

/**
 * Registers the "Sage File" entry in the project-view New menu
 * (right-click a directory -> New -> SageMath -> Sage File).
 *
 * Two platform mechanisms cooperate here:
 * 1. `resources/fileTemplates/Sage File.sage.ft` is picked up by
 *    [com.intellij.ide.fileTemplates.impl.FileTemplatesLoader] from the
 *    plugin jar and becomes a default file template named "Sage File" with
 *    extension "sage" — creating the file through it yields a real `.sage`
 *    file handled by [SageFileType] (so all Sage/Python intelligence applies
 *    immediately).
 * 2. This `com.intellij.fileTemplateGroup` extension makes that template
 *    appear in the New menu under its own "SageMath" group, exactly like the
 *    bundled Maven/DevKit plugins expose their file templates.
 */
class SageFileTemplatesFactory : FileTemplateGroupDescriptorFactory {

    override fun getFileTemplatesDescriptor(): FileTemplateGroupDescriptor {
        val group = FileTemplateGroupDescriptor(SageBundle.message("sage.new.file.group"), SageIcons.SAGE)
        group.addTemplate(object : FileTemplateDescriptor(SAGE_FILE_TEMPLATE, SageIcons.SAGE) {
            /**
             * The New menu shows this text; the file name stays the plain
             * template name so `FileTemplateManager.getTemplate(...)` finds the
             * `fileTemplates/Sage File.sage.ft` resource.  Localized through
             * [SageBundle]: "Sage 文件" on a zh-CN IDE, "Sage File" otherwise
             * (the DevKit plugin localizes its template entries the same way).
             */
            override fun getDisplayName(): String = SageBundle.message("sage.new.file.display")
        })
        return group
    }

    companion object {
        /** Must equal the `fileTemplates/Sage File.sage.ft` resource name minus the `.ft` suffix. */
        const val SAGE_FILE_TEMPLATE: String = "Sage File"
    }
}
