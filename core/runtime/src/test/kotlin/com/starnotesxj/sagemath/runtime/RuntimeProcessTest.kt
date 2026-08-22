package com.starnotesxj.sagemath.runtime

import java.nio.file.Path
import java.time.Duration
import kotlin.concurrent.thread
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class RuntimeProcessTest {
    private val java = Path.of(System.getProperty("java.home"), "bin", if (System.getProperty("os.name").startsWith("Windows")) "java.exe" else "java").toString()
    @Test fun boundedOutput() { val r=JdkRuntimeProcessExecutor().execute(RuntimeProcessRequest(listOf(java,"-version"),maxOutputBytes=8)); assertEquals(RuntimeExecutionStatus.SUCCESS,r.status); assertTrue(r.outputTruncated) }
    @Test fun expiredDeadlinePreventsStart() { val r=JdkRuntimeProcessExecutor().execute(RuntimeProcessRequest(listOf(java,"-version"),control=RuntimeControl(RuntimeDeadline.after(Duration.ZERO)))); assertEquals(RuntimeExecutionStatus.TIMED_OUT,r.status); assertEquals(null,r.exitCode) }
    @Test fun cancellationReturnsCancelled() { val c=MutableRuntimeCancellation(); val t=thread { JdkRuntimeProcessExecutor().execute(RuntimeProcessRequest(listOf(java,"-version"),control=RuntimeControl(cancellation=c))) }; c.cancel(); t.join(5000); assertTrue(!t.isAlive) }
}
