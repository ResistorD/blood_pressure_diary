tasks.register<Delete>("clean") {
    delete(rootProject.layout.buildDirectory)
}

subprojects {
    configurations.all {
        resolutionStrategy.eachDependency {
            // В KTS используются только двойные кавычки ""
            if (requested.group == "androidx.core") {
                useVersion("1.13.1")
            }
        }
    }

    afterEvaluate {
        // Настройка Android через расширения, так как это KTS
        val android = extensions.findByName("android") as? com.android.build.gradle.BaseExtension
        android?.apply {
            if (namespace == null) {
                namespace = project.group.toString()
            }
            compileSdkVersion(36)
            buildToolsVersion("36.0.0")
        }
    }
}