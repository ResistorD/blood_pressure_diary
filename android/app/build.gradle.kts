import java.io.File

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.dmitry.blood_pressure_diary"
    compileSdk = 36
    ndkVersion = flutter.ndkVersion

    defaultConfig {
        applicationId = "com.dmitry.blood_pressure_diary"
        minSdk = 24
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
        setProperty("archivesBaseName", "PressureDiary-v${versionName}")
    }

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.4")
}

afterEvaluate {
    tasks.named("assembleRelease").configure {
        doLast {
            // Где Gradle реально кладёт APK:
            val apk = file("$buildDir/outputs/apk/release/app-release.apk")
            if (!apk.exists()) {
                println("✖ APK not found: ${apk.absolutePath}")
                return@doLast
            }

            // Куда Flutter ожидает APK:
            val flutterOut = rootProject.file("../build/app/outputs/flutter-apk")
            flutterOut.mkdirs()

            // Без java.io.File — просто resolve()
            val dst = flutterOut.resolve("PressureDiary.apk")
            apk.copyTo(dst, overwrite = true)

            println("✔ Mirrored APK to: ${dst.absolutePath}")
        }
    }
}
