plugins {
    kotlin("jvm")
}

kotlin {
    jvmToolchain(25)
}

dependencies {
    implementation(kotlin("stdlib"))
    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnitPlatform()
    enabled = providers.gradleProperty("runSageApiTests").map(String::toBoolean).orElse(false).get()
}
