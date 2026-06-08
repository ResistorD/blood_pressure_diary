import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:isar/isar.dart';
import 'package:path_provider/path_provider.dart';
import 'package:blood_pressure_diary/core/di/service_locator.dart';
import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/core/navigation/app_navigation.dart';
import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';
import 'package:blood_pressure_diary/features/settings/data/models/settings_model.dart';
import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_cubit.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_state.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';

void main() async {
  // ✅ Глобальный error handler для Flutter ошибок
  FlutterError.onError = (FlutterErrorDetails details) {
    FlutterError.presentError(details);
    debugPrint('Flutter Error: ${details.exceptionAsString()}');
  };

  // ✅ Глобальный error handler для async ошибок
  runZonedGuarded(
    () async {
      WidgetsFlutterBinding.ensureInitialized();
      await SystemChrome.setPreferredOrientations([
        DeviceOrientation.portraitUp,
      ]);
      runApp(const BloodPressureAppBootstrap());
    },
    (error, stack) {
      debugPrint('Async Error: $error\n$stack');
    },
  );
}

/// ✅ Bootstrap виджет с явной инициализацией
class BloodPressureAppBootstrap extends StatefulWidget {
  const BloodPressureAppBootstrap({super.key});

  @override
  State<BloodPressureAppBootstrap> createState() => _BloodPressureAppBootstrapState();
}

class _BloodPressureAppBootstrapState extends State<BloodPressureAppBootstrap> {
  Future<void>? _initFuture;

  @override
  void initState() {
    super.initState();
    _initFuture = _initializeApp();
  }

  Future<void> _initializeApp() async {
    try {
      final dir = await getApplicationDocumentsDirectory();
      final isar = await Isar.open(
        [BloodPressureRecordSchema, AppSettingsSchema, UserProfileSchema],
        directory: dir.path,
      );

      await setupLocator(isar);
      await initializeDateFormatting('ru');
      
      // ✅ Safety buffer для гарантии инициализации DI
      await Future.delayed(const Duration(milliseconds: 50));
    } catch (e, stack) {
      debugPrint('Initialization Error: $e\n$stack');
      rethrow;
    }
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _initFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.done) {
          if (snapshot.hasError) {
            return MaterialApp(
              debugShowCheckedModeBanner: false,
              home: Scaffold(
                body: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24.0),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.error_outline, size: 64, color: Colors.red),
                        const SizedBox(height: 16),
                        const Text(
                          'Failed to initialize app',
                          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                          textAlign: TextAlign.center,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          '${snapshot.error}',
                          style: const TextStyle(fontSize: 14, color: Colors.grey),
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }
          return const BloodPressureApp();
        }

        // ✅ Splash Screen
        return MaterialApp(
          debugShowCheckedModeBanner: false,
          home: Scaffold(
            backgroundColor: AppPalette.blue700,
            body: Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.favorite,
                    size: 80,
                    color: Colors.white,
                  ),
                  const SizedBox(height: 24),
                  const Text(
                    'Blood Pressure Diary',
                    style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                    ),
                  ),
                  const SizedBox(height: 32),
                  const SizedBox(
                    width: 40,
                    height: 40,
                    child: CircularProgressIndicator(
                      color: Colors.white,
                      strokeWidth: 3,
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

class BloodPressureApp extends StatelessWidget {
  const BloodPressureApp({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) => getIt<SettingsCubit>(),
      child: BlocBuilder<SettingsCubit, SettingsState>(
        builder: (context, state) {
          return MaterialApp(
            debugShowCheckedModeBanner: false,
            onGenerateTitle: (context) => AppLocalizations.of(context)!.appTitle,
            theme: AppTheme.lightTheme,
            darkTheme: AppTheme.darkTheme,
            themeMode: _getThemeMode(state.settings.themeMode),
            locale: Locale(state.settings.languageCode),
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: AppLocalizations.supportedLocales,

            // ✅ Фиксируем системный масштаб шрифта (для пиксель-перфекта)
            builder: (context, child) {
              final mq = MediaQuery.of(context);
              return MediaQuery(
                data: mq.copyWith(
                  textScaler: const TextScaler.linear(1.0),
                ),
                child: child ?? const SizedBox.shrink(),
              );
            },

            home: const AppNavigation(),
          );
        },
      ),
    );
  }

  ThemeMode _getThemeMode(AppThemeMode mode) {
    switch (mode) {
      case AppThemeMode.light:
        return ThemeMode.light;
      case AppThemeMode.dark:
        return ThemeMode.dark;
      case AppThemeMode.system:
        return ThemeMode.system;
    }
  }
}
