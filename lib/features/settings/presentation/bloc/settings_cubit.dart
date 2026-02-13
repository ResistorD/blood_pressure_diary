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
import 'package:package_info_plus/package_info_plus.dart';

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
    _loadAppVersion();
  }

  Future<void> _loadSettings() async {
    // ✅ Надёжно: всегда получаем singleton-настройки из Isar
    final settings = await _isarService.getOrCreateSettings();
    emit(SettingsState(settings, appVersion: state.appVersion));
  }

  Future<void> _loadAppVersion() async {
    try {
      final info = await PackageInfo.fromPlatform();
      emit(state.copyWith(appVersion: info.version));
    } catch (_) {
      // If platform info is unavailable, keep version null.
    }
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
    emit(state.copyWith(settings: newSettings));
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
    emit(state.copyWith(settings: newSettings));
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

    emit(state.copyWith(settings: newSettings));
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

    // Cancel scheduled notification if it exists
    await _notificationService.cancelNotification(timeStr.hashCode);

    emit(state.copyWith(settings: newSettings));
  }

  Future<void> toggleNotifications(bool enabled) async {
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
      // Reschedule all reminders
      for (final timeStr in newSettings.reminders) {
        final parts = timeStr.split(':');
        if (parts.length != 2) continue;
        final time = TimeOfDay(
          hour: int.parse(parts[0]),
          minute: int.parse(parts[1]),
        );
        await _notificationService.scheduleDailyNotification(timeStr.hashCode, time);
      }
    } else {
      // Cancel all reminders
      for (final timeStr in newSettings.reminders) {
        await _notificationService.cancelNotification(timeStr.hashCode);
      }
    }

    emit(state.copyWith(settings: newSettings));
  }

  Future<void> exportData(ExportFormat format, {int? days}) async {
    final records = await _pressureRepository.getAllRecords();

    // Optional period filter (days). Kept to preserve existing export behavior.
    var effectiveRecords = records;
    if (days != null) {
      final cutoff = DateTime.now().subtract(Duration(days: days));
      effectiveRecords = records.where((r) {
        final dt = r.dateTime;
        return dt.isAfter(cutoff) || dt.isAtSameMomentAs(cutoff);
      }).toList();
    }

    if (effectiveRecords.isEmpty) {
      final message = state.settings.languageCode == 'ru'
          ? 'Нет данных для экспорта'
          : 'No data to export';
      emit(state.copyWith(errorMessage: message));
      emit(state.copyWith(errorMessage: null));
      return;
    }

    // ✅ Строго типобезопасно: профиль берём так, как проектом предусмотрено.
    final profile = await _isarService.getOrCreateProfile();

    emit(state.copyWith(isExporting: true));
    try {
      await _exportService.exportData(
        effectiveRecords,
        format,
        state.settings.languageCode,
        profile: profile,
        periodDays: days ?? 36500,
      );
    } catch (e) {
      final message = state.settings.languageCode == 'ru'
          ? 'Ошибка при экспорте: $e'
          : 'Export error: $e';
      emit(state.copyWith(errorMessage: message));
      emit(state.copyWith(errorMessage: null));
    } finally {
      emit(state.copyWith(isExporting: false));
    }
  }

  // Backwards-compatible positional wrapper (older call sites).
  Future<void> exportDataLegacy(ExportFormat format, [int? days]) async {
    await exportData(format, days: days);
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
