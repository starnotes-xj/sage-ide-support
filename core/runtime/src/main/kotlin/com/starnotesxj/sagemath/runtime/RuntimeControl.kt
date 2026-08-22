package com.starnotesxj.sagemath.runtime

import java.time.Duration
import java.util.concurrent.atomic.AtomicBoolean

/** Monotonic deadline shared by runtime operations. */
class RuntimeDeadline private constructor(private val deadlineNanos: Long?) {
    fun isExpired(nowNanos: Long = System.nanoTime()): Boolean = deadlineNanos?.let { nowNanos >= it } ?: false
    fun remainingNanos(nowNanos: Long = System.nanoTime()): Long? = deadlineNanos?.let { (it - nowNanos).coerceAtLeast(0L) }
    companion object {
        fun unlimited() = RuntimeDeadline(null)
        fun after(duration: Duration, nowNanos: Long = System.nanoTime()): RuntimeDeadline {
            require(!duration.isNegative) { "Runtime deadline duration must not be negative" }
            val nanos = duration.toNanos()
            val end = if (Long.MAX_VALUE - nowNanos < nanos) Long.MAX_VALUE else nowNanos + nanos
            return RuntimeDeadline(end)
        }
    }
}

fun interface RuntimeCancellation { fun isCancelled(): Boolean }
object NeverRuntimeCancelled : RuntimeCancellation { override fun isCancelled() = false }
class MutableRuntimeCancellation : RuntimeCancellation {
    private val value = AtomicBoolean(false)
    override fun isCancelled() = value.get()
    fun cancel() = value.compareAndSet(false, true)
}

enum class RuntimeExecutionStatus { SUCCESS, CANCELLED, TIMED_OUT, FAILED }
data class RuntimeControl(val deadline: RuntimeDeadline = RuntimeDeadline.unlimited(), val cancellation: RuntimeCancellation = NeverRuntimeCancelled) {
    fun status(): RuntimeExecutionStatus? = when { cancellation.isCancelled() -> RuntimeExecutionStatus.CANCELLED; deadline.isExpired() -> RuntimeExecutionStatus.TIMED_OUT; else -> null }
}

/** Throws a stage-specific failure before a blocking runtime operation continues. */
internal fun RuntimeControl.checkpoint(stage: String) {
    when {
        cancellation.isCancelled() -> throw RuntimeInstallException("${stage}_CANCELLED", "Runtime operation was cancelled")
        deadline.isExpired() -> throw RuntimeInstallException("${stage}_TIMED_OUT", "Runtime operation deadline expired")
    }
}

