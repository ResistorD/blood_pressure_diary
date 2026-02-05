// settings_cubit.dart
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:in_app_review/in_app_review.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/core/repositories/pressure_repository.dart';
import 'package:blood_pressure_diary/core/services/export_service.dart';
import 'package:blood_pressure_diary/core/services/notification_service.dart';
import 'package:blood_pressure_diary/features/settings/data/models/settings_model.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_state.dart';

class SettingsCubit extends Cubit<SettingsState> {
  final IsarService _isarService;
  final PressureRepository _pressureRepository;
  final ExportService _exportService;
  final NotificationService _notificationService;

  StreamSubscription<AppSettings>? _settingsSub;

  SettingsCubit(
      this._isarService,
      this._pressureRepository,
      this._exportService,
      this._notificationService,
      ) : super(SettingsState(AppSettings())) {
    _bind();
  }

  Future<void> _bind() async {
    await _isarService.getOrCreateSettings();

    await _settingsSub?.cancel();
    _settingsSub = _isarService.watchSettings().listen((settings) {
      emit(SettingsState(
        settings,
        errorMessage: state.errorMessage,
        isExporting: state.isExporting,
      ));
    });
  }

  @override
  Future<void> close() async {
    await _settingsSub?.cancel();
    return super.close();
  }

  Future<void> changeLanguage(String langCode) async {
    final s = state.settings;
    final updated = AppSettings(
      themeMode: s.themeMode,
      languageCode: langCode,
      reminders: s.reminders,
      notificationsEnabled: s.notificationsEnabled,
      accountLinked: s.accountLinked,
      accountEmail: s.accountEmail,
      accountProvider: s.accountProvider,
    );
    await _isarService.saveSettings(updated);
  }

  Future<void> setThemeMode(AppThemeMode mode) async {
    final s = state.settings;
    final updated = AppSettings(
      themeMode: mode, // ✅ ВОТ ЭТО и ломало переключение
      languageCode: s.languageCode,
      reminders: s.reminders,
      notificationsEnabled: s.notificationsEnabled,
      accountLinked: s.accountLinked,
      accountEmail: s.accountEmail,
      accountProvider: s.accountProvider,
    );
    await _isarService.saveSettings(updated);
  }

  Future<void> addReminder(TimeOfDay time) async {
    final hour = time.hour.toString().padLeft(2, '0');
    final minute = time.minute.toString().padLeft(2, '0');
    final timeStr = '$hour:$minute';

    final s = state.settings;
    if (s.reminders.contains(timeStr)) return;

    final newList = List<String>.from(s.reminders)..add(timeStr);
    newList.sort();

    final updated = AppSettings(
      themeMode: s.themeMode,
      languageCode: s.languageCode,
      reminders: newList,
      notificationsEnabled: s.notificationsEnabled,
      accountLinked: s.accountLinked,
      accountEmail: s.accountEmail,
      accountProvider: s.accountProvider,
    );

    await _isarService.saveSettings(updated);

    if (s.notificationsEnabled) {
      await _notificationService.scheduleDailyNotification(timeStr.hashCode, time);
    }
  }

  Future<void> removeReminder(int index) async {
    final s = state.settings;
    if (index < 0 || index >= s.reminders.length) return;

    final timeStr = s.reminders[index];
    final newList = List<String>.from(s.reminders)..removeAt(index);

    final updated = AppSettings(
      themeMode: s.themeMode,
      languageCode: s.languageCode,
      reminders: newList,
      notificationsEnabled: s.notificationsEnabled,
      accountLinked: s.accountLinked,
      accountEmail: s.accountEmail,
      accountProvider: s.accountProvider,
    );

    await _isarService.saveSettings(updated);

    if (s.notificationsEnabled) {
      await _notificationService.cancelNotification(timeStr.hashCode);
    }
  }

  Future<void> toggleNotifications(bool enabled) async {
    final s = state.settings;

    if (enabled) {
      final granted = await _notificationService.requestPermissions();
      if (!granted) {
        final message = s.languageCode == 'ru'
            ? 'Разрешение на уведомления не получено'
            : 'Notification permission not granted';
        emit(state.copyWith(errorMessage: message));
        emit(state.copyWith(errorMessage: null));
        return;
      }
    }

    final reminders = (enabled && s.reminders.isEmpty)
        ? <String>['08:00', '20:00']
        : List<String>.from(s.reminders);

    reminders.sort();

    final updated = AppSettings(
      themeMode: s.themeMode,
      languageCode: s.languageCode,
      reminders: reminders,
      notificationsEnabled: enabled,
      accountLinked: s.accountLinked,
      accountEmail: s.accountEmail,
      accountProvider: s.accountProvider,
    );

    await _isarService.saveSettings(updated);

    if (enabled) {
      await _syncAllNotifications(reminders);
    } else {
      await _notificationService.cancelAllNotifications();
    }
  }

  Future<void> _syncAllNotifications(List<String> reminders) async {
    await _notificationService.cancelAllNotifications();

    for (final timeStr in reminders) {
      final parts = timeStr.split(':');
      final time = TimeOfDay(
        hour: int.parse(parts[0]),
        minute: int.parse(parts[1]),
      );
      await _notificationService.scheduleDailyNotification(timeStr.hashCode, time);
    }
  }

  /// periodDays используется для PDF (например, 14 дней), для CSV можно передавать 0.
  Future<void> exportData(ExportFormat format, {int pdfPeriodDays = 14}) async {
    final records = await _pressureRepository.getAllRecords();

    if (records.isEmpty) {
      final message = state.settings.languageCode == 'ru'
          ? 'Нет данных для экспорта'
          : 'No data to export';
      emit(state.copyWith(errorMessage: message));
      emit(state.copyWith(errorMessage: null));
      return;
    }

    UserProfile? profile;
    try {
      profile = await _isarService.getOrCreateProfile();
    } catch (_) {
      profile = null;
    }

    emit(state.copyWith(isExporting: true));
    try {
      await _exportService.exportData(
        records,
        format,
        state.settings.languageCode,
        profile: profile,
        periodDays: format == ExportFormat.pdf ? pdfPeriodDays : 0,
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
    final inAppReview = InAppReview.instance;
    if (await inAppReview.isAvailable()) {
      await inAppReview.requestReview();
    }
  }
}
