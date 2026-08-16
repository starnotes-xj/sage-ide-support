package com.starnotesxj.sageide.sugar

import com.jetbrains.python.psi.PyFileElementType

/**
 * File element type for the Sage dialect.  Without it,
 * [PyFileElementType.parseContents] finds no parser definition for the
 * dialect language and the file would not parse at all.
 */
class SageFileElementType private constructor() : PyFileElementType(SageLanguage.INSTANCE) {
    override fun getExternalId(): String = "Sage.FILE"

    companion object {
        @JvmField
        val INSTANCE: SageFileElementType = SageFileElementType()
    }
}
