package com.starnotesxj.sagemath.runtime

import java.nio.file.Path
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNotNull

class RuntimeProbeTest {
 @Test fun probeRunsVersionAndExpression() {
  val calls=mutableListOf<List<String>>(); val executor=RuntimeProcessExecutor { request -> calls+=request.command; RuntimeProcessResult(RuntimeExecutionStatus.SUCCESS,0,if(calls.size==1) "SageMath version 10.6" else "4\n","",1,false) }
  val r=RuntimeProbe(executor).probe(RuntimeProbeRequest(Path.of("sage")))
  assertEquals(RuntimeExecutionStatus.SUCCESS,r.status); assertEquals("SageMath version 10.6",r.version); assertEquals("4",r.expressionOutput)
  assertNotNull(calls.singleOrNull { it.contains("--version") }); assertNotNull(calls.singleOrNull { it.contains("print(2+2)") })
 }
}
