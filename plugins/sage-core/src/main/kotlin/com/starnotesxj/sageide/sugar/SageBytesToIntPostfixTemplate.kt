package com.starnotesxj.sageide.sugar

import com.intellij.codeInsight.template.postfix.templates.PostfixTemplateProvider

/**
 * `.b2i` -> `int.from_bytes(expr, "big")` — CTF bytes-to-int conversion.
 * Own class so the `postfixTemplates/SageBytesToIntPostfixTemplate/`
 * description/example resources resolve from this plugin.
 */
class SageBytesToIntPostfixTemplate(provider: PostfixTemplateProvider) : SageFixedPostfixTemplate(
    name = "int.from_bytes(expr, 'big')",
    key = ".b2i",
    example = "int.from_bytes(expr, 'big')",
    // $expr$ references the target expression — the platform's
    // StringBasedPostfixTemplate.EXPR convention for built-in templates
    // (user-created templates in the editor use $EXPR$ instead).
    templateText = "int.from_bytes(\$expr\$, \"big\")\$END\$",
    provider = provider,
)
