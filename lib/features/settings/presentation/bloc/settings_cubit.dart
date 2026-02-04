// settings_cubit.dart (минимальная замена: добавлен период как параметр exportData)
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

  StreamSubscription<AppSettings>? _settingsSub;

  SettingsCubit({
    required IsarService isarService,
    required PressureRepository pressureRepository,
    required ExportService exportService,
  })  : _isarService = isarService,
        _pressureRepository = pressureRepository,
        _exportService = exportService,
        super(SettingsState(AppSettings()));

  Future<void> init() async {
    // гарантия наличия singleton настроек
    final s = await _isarService.getOrCreateSettings();
    emit(SettingsState(s));

    _settingsSub?.cancel();
    _settingsSub = _isarService.watchSettings().listen((settings) {
      emit(SettingsState(settings));
    });
  }

  @override
  Future<void> close() {
    _settingsSub?.cancel();
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
      themeMode: mode, // ✅ ВОТ ЭТО БЫЛО НЕПРАВИЛЬНО
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

    // обновим планировщик уведомлений
    await NotificationService().scheduleReminders(newList);
  }

  Future<void> removeReminder(String timeStr) async {
    final s = state.settings;
    if (!s.reminders.contains(timeStr)) return;

    final newList = List<String>.from(s.reminders)..remove(timeStr);

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

    await NotificationService().scheduleReminders(newList);
  }

  Future<void> toggleNotifications(bool enabled) async {
    final s = state.settings;

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
      await NotificationService().scheduleReminders(s.reminders);
    } else {
      await NotificationService().cancelAll();
    }
  }

  Future<void> exportData({
    required ExportFormat format,
    required ExportPeriod period,
  }) async {
    try {
      emit(state.copyWith(isExporting: true, errorMessage: null));
      await _exportService.export(format: format, period: period);
      emit(state.copyWith(isExporting: false));
    } catch (e) {
      emit(state.copyWith(isExporting: false, errorMessage: e.toString()));
    }
  }

  Future<void> clearAllData() async {
    try {
      await _pressureRepository.clearAll();
    } catch (_) {}
  }

  Future<void> rateApp(String packageName) async {
    try {
      final inAppReview = InAppReview.instance;
      if (await inAppReview.isAvailable()) {
        await inAppReview.requestReview();
        return;
      }
    } catch (_) {}

    final uriMarket = Uri.parse('market://details?id=$packageName');
    final uriWeb = Uri.parse('https://play.google.com/store/apps/details?id=$packageName');

    if (await canLaunchUrl(uriMarket)) {
      await launchUrl(uriMarket);
    } else if (await canLaunchUrl(uriWeb)) {
      await launchUrl(uriWeb, mode: LaunchMode.externalApplication);
    }
  }

  Future<void> writeToUs({
    required String email,
    required String subject,
    required String body,
  }) async {
    final uri = Uri(
      scheme: 'mailto',
      path: email,
      queryParameters: {
        'subject': subject,
        'body': body,
      },
    );
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri);
    }
  }
}
