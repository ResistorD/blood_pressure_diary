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

  AppSettings({
    this.themeMode = AppThemeMode.light,
    this.languageCode = 'ru',
    this.reminders = const [],
    this.notificationsEnabled = false,
  });
}

enum AppThemeMode {
  light,
  dark,
  system,
}
