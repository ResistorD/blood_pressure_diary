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
    reloadSettings();
    _loadAppVersion();
  }

  Future<void> reloadSettings() async {
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
    final newSettings = state.settings.copyWith(languageCode: langCode);
    await _isarService.saveSettings(newSettings);
    emit(state.copyWith(settings: newSettings));
  }

  Future<void> setThemeMode(AppThemeMode mode) async {
    final newSettings = state.settings.copyWith(themeMode: mode);
    await _isarService.saveSettings(newSettings);
    emit(state.copyWith(settings: newSettings));
  }

  Future<void> addReminder(TimeOfDay time) async {
    if (!state.settings.notificationsEnabled) return;

    final hour = time.hour.toString().padLeft(2, '0');
    final minute = time.minute.toString().padLeft(2, '0');
    final timeStr = "$hour:$minute";

    if (state.settings.reminders.contains(timeStr)) return;

    final newList = List<String>.from(state.settings.reminders)..add(timeStr);
    newList.sort();

    final newSettings = state.settings.copyWith(reminders: newList);
    await _isarService.saveSettings(newSettings);
    emit(state.copyWith(settings: newSettings));

    try {
      await _notificationService.scheduleDailyNotification(
        timeStr.hashCode,
        time,
        languageCode: state.settings.languageCode,
      );
    } catch (e) {
      debugPrint('Schedule reminder notification error: $e');
    }
  }

  Future<void> removeReminder(int index) async {
    if (!state.settings.notificationsEnabled) return;
    if (index < 0 || index >= state.settings.reminders.length) return;

    final timeStr = state.settings.reminders[index];
    final newList = List<String>.from(state.settings.reminders)
      ..removeAt(index);

    final newSettings = state.settings.copyWith(reminders: newList);
    await _isarService.saveSettings(newSettings);
    emit(state.copyWith(settings: newSettings));

    try {
      await _notificationService.cancelNotification(timeStr.hashCode);
    } catch (e) {
      debugPrint('Cancel reminder notification error: $e');
    }
  }

  Future<void> updateReminder(int index, TimeOfDay time) async {
    if (!state.settings.notificationsEnabled) return;
    if (index < 0 || index >= state.settings.reminders.length) return;

    final hour = time.hour.toString().padLeft(2, '0');
    final minute = time.minute.toString().padLeft(2, '0');
    final newTimeStr = "$hour:$minute";
    final oldTimeStr = state.settings.reminders[index];

    final newList = List<String>.from(state.settings.reminders);
    final duplicateIndex = newList.indexOf(newTimeStr);
    if (duplicateIndex != -1 && duplicateIndex != index) return;

    newList[index] = newTimeStr;
    newList.sort();

    final newSettings = state.settings.copyWith(reminders: newList);
    await _isarService.saveSettings(newSettings);
    emit(state.copyWith(settings: newSettings));

    try {
      await _notificationService.cancelNotification(oldTimeStr.hashCode);
      await _notificationService.scheduleDailyNotification(
        newTimeStr.hashCode,
        time,
        languageCode: state.settings.languageCode,
      );
    } catch (e) {
      debugPrint('Update reminder notification error: $e');
    }
  }

  Future<void> toggleNotifications(bool enabled) async {
    final newSettings = state.settings.copyWith(notificationsEnabled: enabled);
    await _isarService.saveSettings(newSettings);
    emit(state.copyWith(settings: newSettings));

    if (enabled) {
      // Reschedule all reminders
      for (final timeStr in newSettings.reminders) {
        final parts = timeStr.split(':');
        if (parts.length != 2) continue;
        final time = TimeOfDay(
          hour: int.parse(parts[0]),
          minute: int.parse(parts[1]),
        );
        try {
          await _notificationService.scheduleDailyNotification(
            timeStr.hashCode,
            time,
            languageCode: state.settings.languageCode,
          );
        } catch (e) {
          debugPrint('Schedule reminder notification error: $e');
        }
      }
    } else {
      // Cancel all reminders
      for (final timeStr in newSettings.reminders) {
        try {
          await _notificationService.cancelNotification(timeStr.hashCode);
        } catch (e) {
          debugPrint('Cancel reminder notification error: $e');
        }
      }
    }
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
    final Uri uri = Uri(
      scheme: 'mailto',
      path: 'resistor.rs@gmail.com', // ✅ твой реальный адрес
      queryParameters: <String, String>{
        'subject': 'Pressure Diary — обратная связь',
        'body': 'Опишите проблему или предложение.\n',
      },
    );

    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } else {
      // если хочешь — можно эмитить errorMessage
      // emit(state.copyWith(errorMessage: 'Не удалось открыть почту'));
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
