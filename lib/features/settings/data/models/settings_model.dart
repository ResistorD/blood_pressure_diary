import 'package:isar/isar.dart';

part 'settings_model.g.dart';

@collection
class AppSettings {
  Id id = 0; // Всегда 0, так как у нас только одна запись настроек

  @enumerated
  AppThemeMode themeMode = AppThemeMode.light;

  String languageCode = 'ru';

  List<String> reminders = [];

  bool notificationsEnabled = false;

  // --- Account (локальная привязка аккаунта)
  // Сейчас это простой "профиль привязки" (email/провайдер) без реальной авторизации.
  // Нужен, чтобы экран Профиля мог "войти/выйти" и в будущем использовать синхронизацию.
  bool accountLinked = false;
  String accountEmail = '';
  String accountProvider = ''; // например: 'email', 'google', 'apple'

  AppSettings({
    this.themeMode = AppThemeMode.light,
    this.languageCode = 'ru',
    this.reminders = const [],
    this.notificationsEnabled = false,
    this.accountLinked = false,
    this.accountEmail = '',
    this.accountProvider = '',
  });
}

enum AppThemeMode {
  light,
  dark,
  system,
}
