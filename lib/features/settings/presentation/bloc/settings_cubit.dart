import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:in_app_review/in_app_review.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:blood_pressure_diary/core/database/isar_service.dart';
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
    // 1) Гарантируем, что singleton-настройки существуют.
    await _isarService.getOrCreateSettings();

    // 2) Держим один источник истины: Isar → Cubit.
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
      themeMode: mode,
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

    // Нотификации синхронизируем уже после записи.
    if (s.notificationsEnabled) {
      final id = timeStr.hashCode;
      await _notificationService.scheduleDailyNotification(id, time);
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

    final updated = AppSettings(
      themeMode: s.themeMode,
      languageCode: s.languageCode,
      reminders: s.reminders,
      notificationsEnabled: enabled,
      accountLinked: s.accountLinked,
      accountEmail: s.accountEmail,
      accountProvider: s.accountProvider,
    );

    await _isarService.saveSettings(updated);

    if (enabled) {
      await _syncAllNotifications(s.reminders);
    } else {
      await _notificationService.cancelAllNotifications();
    }
  }

  Future<void> _syncAllNotifications(List<String> reminders) async {
    await _notificationService.cancelAllNotifications();
    for (final r in reminders) {
      final parts = r.split(':');
      if (parts.length == 2) {
        final h = int.tryParse(parts[0]);
        final m = int.tryParse(parts[1]);
        if (h != null && m != null) {
          await _notificationService.scheduleDailyNotification(
            r.hashCode,
            TimeOfDay(hour: h, minute: m),
          );
        }
      }
    }
  }

  Future<void> exportData() async {
    emit(state.copyWith(isExporting: true));
    try {
      final records = await _pressureRepository.getAllRecords();
      await _exportService.exportToCsv(records);
    } catch (e) {
      emit(state.copyWith(errorMessage: e.toString()));
      emit(state.copyWith(errorMessage: null));
    } finally {
      emit(state.copyWith(isExporting: false));
    }
  }

  Future<void> rateApp() async {
    final InAppReview inAppReview = InAppReview.instance;
    if (await inAppReview.isAvailable()) {
      await inAppReview.requestReview();
    }
  }

  Future<void> contactSupport() async {
    final Uri emailLaunchUri = Uri(
      scheme: 'mailto',
      path: 'support@example.com',
      queryParameters: {
        'subject': 'Blood Pressure Diary Support',
      },
    );
    if (await canLaunchUrl(emailLaunchUri)) {
      await launchUrl(emailLaunchUri);
    }
  }
}
