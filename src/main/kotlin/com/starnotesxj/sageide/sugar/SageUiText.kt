package com.starnotesxj.sageide.sugar

import com.intellij.DynamicBundle

/**
 * User-visible entry text for the "create a Sage file" actions.
 *
 * The IDE locale is read directly from [DynamicBundle.getLocale] (the
 * `i18n.locale` service value) instead of a localized ResourceBundle: the
 * New-menu pipeline for file templates shows `FileTemplate.getName()` and the
 * `createFromTemplateActionReplacer` action text — neither consults plugin
 * properties bundles — so a plain locale check is the reliable way to show
 * "Sage 文件" on a zh-CN IDE and "Sage File" otherwise.
 */
object SageUiText {

    @JvmStatic
    fun sageFileEntry(): String = if (DynamicBundle.getLocale().language == "zh") "Sage 文件" else "Sage File"

    @JvmStatic
    fun sageGroupName(): String = "SageMath"
}
