package com.starnotesxj.sageide.sugar

import com.starnotesxj.sageide.SageBundle

/**
 * User-visible entry text for the "create a Sage file" actions.
 *
 * The action replacer resolves the current IDE locale through [SageBundle],
 * because the underlying file-template resource name itself is not localized.
 */
object SageUiText {

    @JvmStatic
    fun sageFileEntry(): String = SageBundle.message("sage.file.entry")

    @JvmStatic
    fun sageGroupName(): String = "SageMath"
}
