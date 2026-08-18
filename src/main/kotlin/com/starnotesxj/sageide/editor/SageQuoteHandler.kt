package com.starnotesxj.sageide.editor

import com.jetbrains.python.editor.PythonQuoteHandler

/**
 * Quote typing handler for `.sage` files.
 *
 * The platform's quoteHandler extension point resolves the handler for the
 * language AT THE CARET — the Sage dialect — and does not fall back to base
 * languages, so Python's handler (registered for "Python" only) never fired
 * in .sage files: typing `"` inserted a single character instead of the pair.
 *
 * Subclassing [PythonQuoteHandler] (which implements
 * `MultiCharQuoteHandler`) inherits Python's behavior unchanged: quote pairs
 * with the caret inside, skipping over an existing closing quote, and
 * triple-quote completion — exactly what .py files do.
 */
class SageQuoteHandler : PythonQuoteHandler()
