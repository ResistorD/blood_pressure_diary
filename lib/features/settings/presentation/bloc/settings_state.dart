import 'package:equatable/equatable.dart';
import '../../data/models/settings_model.dart';

class SettingsState extends Equatable {
  final AppSettings settings;
  final String? errorMessage;
  final bool isExporting;

  const SettingsState(this.settings, {this.errorMessage, this.isExporting = false});

  SettingsState copyWith({
    AppSettings? settings,
    String? errorMessage,
    bool? isExporting,
  }) {
    return SettingsState(
      settings ?? this.settings,
      errorMessage: errorMessage,
      isExporting: isExporting ?? this.isExporting,
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
  ];
}
