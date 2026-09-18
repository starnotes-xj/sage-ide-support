plugins {
    kotlin("jvm") version "2.3.0" apply false
    id("org.jetbrains.intellij.platform") version "2.18.1" apply false
}

group = "com.starnotesxj"
// Keep this above the public Sage IDE Support 1.7.9 release.  The plugin
// module deliberately retains that plugin's Marketplace ID so this is an
// in-place upgrade rather than a second, conflicting installation.
version = "1.8.7"

allprojects {
    group = rootProject.group
    version = rootProject.version
}

subprojects {
    repositories {
        mavenCentral()
    }
}

tasks.register("printProductStatus") {
    group = "verification"
    description = "Prints the current standalone IDE migration status."
    doLast {
        println("SageMath CTF IDE ${project.version}")
        println("Plugin baseline: plugins/sage-core")
        println("Product build: external IntelliJ Community checkout (see product/README.zh-CN.md)")
    }
}
