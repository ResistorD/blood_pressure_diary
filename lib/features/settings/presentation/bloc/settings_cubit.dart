import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/repositories/pressure_repository.dart';
import 'package:blood_pressure_diary/features/settings/data/models/settings_model.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_state.dart';
import 'package:blood_pressure_diary/core/services/export_service.dart';
import 'package:blood_pressure_diary/core/services/notification_service.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:in_app_review/in_app_review.dart';

class SettingsCubit extends Cubit<SettingsState> {
  final IsarService _isarService;
  final PressureRepository _pressureRepository;
  final ExportService _exportService;
  final NotificationService _notificationService;

  SettingsCubit(
      this._isarService,
      this._pressureRepository,
      this._exportService,
      this._notificationService,
      ) : super(SettingsState(AppSettings())) {
    _loadSettings();
  }

  Future<void> _loadSettings() async {
    // ✅ Надёжно: всегда получаем singleton-настройки из Isar
    final settings = await _isarService.getOrCreateSettings();
    emit(SettingsState(settings));
  }

  Future<void> changeLanguage(String langCode) async {
    final newSettings = AppSettings(
      themeMode: state.settings.themeMode,
      languageCode: langCode,
      reminders: state.settings.reminders,
      notificationsEnabled: state.settings.notificationsEnabled,
      accountLinked: state.settings.accountLinked,
      accountEmail: state.settings.accountEmail,
      accountProvider: state.settings.accountProvider,
    );

    await _isarService.saveSettings(newSettings);
    emit(SettingsState(newSettings));
  }

  Future<void> setThemeMode(AppThemeMode mode) async {
    final newSettings = AppSettings(
      themeMode: mode,
      languageCode: state.settings.languageCode,
      reminders: state.settings.reminders,
      notificationsEnabled: state.settings.notificationsEnabled,
      accountLinked: state.settings.accountLinked,
      accountEmail: state.settings.accountEmail,
      accountProvider: state.settings.accountProvider,
    );

    await _isarService.saveSettings(newSettings);
    emit(SettingsState(newSettings));
  }

  Future<void> addReminder(TimeOfDay time) async {
    final hour = time.hour.toString().padLeft(2, '0');
    final minute = time.minute.toString().padLeft(2, '0');
    final timeStr = "$hour:$minute";

    if (state.settings.reminders.contains(timeStr)) return;

    final newList = List<String>.from(state.settings.reminders)..add(timeStr);
    newList.sort();

    final newSettings = AppSettings(
      themeMode: state.settings.themeMode,
      languageCode: state.settings.languageCode,
      reminders: newList,
      notificationsEnabled: state.settings.notificationsEnabled,
      accountLinked: state.settings.accountLinked,
      accountEmail: state.settings.accountEmail,
      accountProvider: state.settings.accountProvider,
    );

    await _isarService.saveSettings(newSettings);

    if (state.settings.notificationsEnabled) {
      final id = timeStr.hashCode;
      await _notificationService.scheduleDailyNotification(id, time);
    }

    emit(SettingsState(newSettings));
  }

  Future<void> removeReminder(int index) async {
    if (index < 0 || index >= state.settings.reminders.length) return;

    final timeStr = state.settings.reminders[index];
    final newList = List<String>.from(state.settings.reminders)..removeAt(index);

    final newSettings = AppSettings(
      themeMode: state.settings.themeMode,
      languageCode: state.settings.languageCode,
      reminders: newList,
      notificationsEnabled: state.settings.notificationsEnabled,
      accountLinked: state.settings.accountLinked,
      accountEmail: state.settings.accountEmail,
      accountProvider: state.settings.accountProvider,
    );

    await _isarService.saveSettings(newSettings);

    if (state.settings.notificationsEnabled) {
      await _notificationService.cancelNotification(timeStr.hashCode);
    }

    emit(SettingsState(newSettings));
  }

  Future<void> toggleNotifications(bool enabled) async {
    if (enabled) {
      final granted = await _notificationService.requestPermissions();
      if (!granted) {
        final message = state.settings.languageCode == 'ru'
            ? 'Разрешение на уведомления не получено'
            : 'Notification permission not granted';
        emit(state.copyWith(errorMessage: message));
        emit(state.copyWith(errorMessage: null));
        return;
      }
    }

    final newSettings = AppSettings(
      themeMode: state.settings.themeMode,
      languageCode: state.settings.languageCode,
      reminders: state.settings.reminders,
      notificationsEnabled: enabled,
      accountLinked: state.settings.accountLinked,
      accountEmail: state.settings.accountEmail,
      accountProvider: state.settings.accountProvider,
    );

    await _isarService.saveSettings(newSettings);

    if (enabled) {
      await _syncAllNotifications(state.settings.reminders);
    } else {
      await _notificationService.cancelAllNotifications();
    }

    emit(SettingsState(newSettings));
  }

  Future<void> _syncAllNotifications(List<String> reminders) async {
    await _notificationService.cancelAllNotifications();
    for (final timeStr in reminders) {
      final parts = timeStr.split(':');
      final time = TimeOfDay(hour: int.parse(parts[0]), minute: int.parse(parts[1]));
      await _notificationService.scheduleDailyNotification(timeStr.hashCode, time);
    }
  }

  Future<void> exportData(ExportFormat format) async {
    final records = await _pressureRepository.getAllRecords();

    if (records.isEmpty) {
      final message = state.settings.languageCode == 'ru' ? 'Нет данных для экспорта' : 'No data to export';
      emit(state.copyWith(errorMessage: message));
      emit(state.copyWith(errorMessage: null));
      return;
    }

    emit(state.copyWith(isExporting: true));
    try {
      await _exportService.exportData(records, format, state.settings.languageCode);
    } catch (e) {
      final message = state.settings.languageCode == 'ru' ? 'Ошибка при экспорте: $e' : 'Export error: $e';
      emit(state.copyWith(errorMessage: message));
      emit(state.copyWith(errorMessage: null));
    } finally {
      emit(state.copyWith(isExporting: false));
    }
  }

  Future<void> clearAllData() async {
    await _pressureRepository.deleteAllRecords();
  }

  Future<void> contactSupport() async {
    final Uri emailLaunchUri = Uri(
      scheme: 'mailto',
      path: 'your_email@mail.com',
      query: 'subject=Blood Pressure Diary Feedback',
    );
    if (await canLaunchUrl(emailLaunchUri)) {
      await launchUrl(emailLaunchUri);
    }
  }

  Future<void> rateApp() async {
    final InAppReview inAppReview = InAppReview.instance;
    if (await inAppReview.isAvailable()) {
      await inAppReview.requestReview();
    } else {
      await inAppReview.openStoreListing();
    }
  }
}
