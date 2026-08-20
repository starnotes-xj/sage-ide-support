package com.starnotesxj.sageide.sugar

import com.intellij.openapi.util.IconLoader
import javax.swing.Icon

object SageIcons {
    // Same file icon the community SageMath plugin (renpe/intellij-sagemath,
    // Apache 2.0) uses: the official SageMath icosahedron logo, CC-BY-SA-4.0.
    @JvmField
    val SAGE: Icon = IconLoader.getIcon("icons/sagemath.png", SageIcons::class.java)
}
