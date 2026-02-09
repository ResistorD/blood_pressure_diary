import 'package:equatable/equatable.dart';
import '../../data/models/settings_model.dart';

class SettingsState extends Equatable {
  final AppSettings settings;
  final String? errorMessage;
  final bool isExporting;
  /// App version from platform package info (e.g. "1.0.0").
  final String? appVersion;

  const SettingsState(
      this.settings, {
        this.errorMessage,
        this.isExporting = false,
        this.appVersion,
      });

  SettingsState copyWith({
    AppSettings? settings,
    String? errorMessage,
    bool? isExporting,
    String? appVersion,
  }) {
    return SettingsState(
      settings ?? this.settings,
      errorMessage: errorMessage,
      isExporting: isExporting ?? this.isExporting,
      appVersion: appVersion ?? this.appVersion,
    );
  }

  @override
  List<Object?> get props => [
    settings.themeMode,
    settings.languageCode,
    settings.notificationsEnabled,
    settings.reminders.join('|'),
    settings.accountLinked,
    settings.accountEmail,
    settings.accountProvider,
    errorMessage,
    isExporting,
    appVersion,
  ];
}
