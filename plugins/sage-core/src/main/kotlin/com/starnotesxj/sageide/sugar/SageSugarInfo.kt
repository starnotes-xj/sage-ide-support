package com.starnotesxj.sageide.sugar

import com.jetbrains.python.psi.PyAssignmentStatement
import com.jetbrains.python.psi.PyCallExpression
import com.jetbrains.python.psi.PyTargetExpression

/**
 * Extracted view of a Sage generator statement, e.g. `F.<a> = GF(2^8, ...)`
 * as parsed by the Sage parser (a multi-target assignment whose targets are
 * `[F, a]`).
 *
 * [factoryTarget] is the ring/parent target (`F`), [nameTargets] the
 * generator targets (`a`), and [call] the constructor call on the right
 * (`GF(...)`), or null while the user is still typing the right-hand side.
 */
class SageSugarInfo(
    val statement: PyAssignmentStatement,
    val factoryTarget: PyTargetExpression,
    val call: PyCallExpression?,
    val nameTargets: List<PyTargetExpression>,
) {
    val factoryName: String = factoryTarget.name ?: factoryTarget.text
    val names: List<String> = nameTargets.map { it.name ?: it.text }
}
