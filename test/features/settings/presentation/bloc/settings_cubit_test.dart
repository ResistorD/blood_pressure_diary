import 'dart:async';

import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/core/repositories/pressure_repository.dart';
import 'package:blood_pressure_diary/core/services/export_service.dart';
import 'package:blood_pressure_diary/core/services/notification_service.dart';
import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_cubit.dart';
import 'package:blood_pressure_diary/features/settings/data/models/settings_model.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_cubit.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  late _FakeIsarService isarService;
  late _CapturingExportService exportService;
  late NotificationService notificationService;
  late SettingsCubit cubit;

  setUp(() async {
    isarService = _FakeIsarService();
    exportService = _CapturingExportService();
    notificationService = _FakeNotificationService();
    cubit = SettingsCubit(
      isarService,
      PressureRepository(isarService),
      exportService,
      notificationService,
    );
    await cubit.reloadSettings();
  });

  tearDown(() async {
    await cubit.close();
  });

  test('toggle reminders off keeps notificationsEnabled false', () async {
    isarService.settings = AppSettings(notificationsEnabled: true);
    await cubit.reloadSettings();

    await cubit.toggleNotifications(false);

    expect(cubit.state.settings.notificationsEnabled, isFalse);
    expect(isarService.settings.notificationsEnabled, isFalse);
  });

  test('toggle reminders on sets notificationsEnabled true', () async {
    await cubit.toggleNotifications(true);

    expect(cubit.state.settings.notificationsEnabled, isTrue);
    expect(isarService.settings.notificationsEnabled, isTrue);
  });

  test(
    'addReminder does not change reminders when notifications are off',
    () async {
      await cubit.addReminder(const TimeOfDay(hour: 9, minute: 30));

      expect(cubit.state.settings.reminders, isEmpty);
      expect(isarService.settings.reminders, isEmpty);
    },
  );

  test(
    'updateReminder does not change reminders when notifications are off',
    () async {
      isarService.settings = AppSettings(reminders: ['08:00']);
      await cubit.reloadSettings();

      await cubit.updateReminder(0, const TimeOfDay(hour: 7, minute: 45));

      expect(cubit.state.settings.reminders, ['08:00']);
      expect(isarService.settings.reminders, ['08:00']);
    },
  );

  test(
    'addReminder adds and persists reminder when notifications are on',
    () async {
      await cubit.toggleNotifications(true);

      await cubit.addReminder(const TimeOfDay(hour: 9, minute: 30));

      expect(cubit.state.settings.reminders, ['09:30']);
      expect(isarService.settings.reminders, ['09:30']);

      await cubit.reloadSettings();
      expect(cubit.state.settings.reminders, ['09:30']);
    },
  );

  test(
    'updateReminder edits reminder immutably when notifications are on',
    () async {
      await cubit.toggleNotifications(true);
      await cubit.addReminder(const TimeOfDay(hour: 8, minute: 0));
      final previousSettings = cubit.state.settings;

      await cubit.updateReminder(0, const TimeOfDay(hour: 7, minute: 45));

      expect(previousSettings.reminders, ['08:00']);
      expect(cubit.state.settings.reminders, ['07:45']);
      expect(isarService.settings.reminders, ['07:45']);
    },
  );

  test(
    'updateReminder keeps default reminder entry instead of deleting it',
    () async {
      await cubit.toggleNotifications(true);
      await cubit.addReminder(const TimeOfDay(hour: 8, minute: 0));
      await cubit.addReminder(const TimeOfDay(hour: 20, minute: 0));

      await cubit.updateReminder(0, const TimeOfDay(hour: 7, minute: 30));

      expect(cubit.state.settings.reminders, ['07:30', '20:00']);
      expect(isarService.settings.reminders, ['07:30', '20:00']);
    },
  );

  test('save/reload keeps switch state and reminders list', () async {
    await cubit.toggleNotifications(true);
    await cubit.addReminder(const TimeOfDay(hour: 8, minute: 0));
    await cubit.reloadSettings();

    expect(cubit.state.settings.notificationsEnabled, isTrue);
    expect(cubit.state.settings.reminders, ['08:00']);
  });

  test(
    'enabled add/edit/delete update state even when notification API fails',
    () async {
      await cubit.close();
      notificationService = _ThrowingNotificationService();
      cubit = SettingsCubit(
        isarService,
        PressureRepository(isarService),
        exportService,
        notificationService,
      );
      await cubit.reloadSettings();

      await cubit.toggleNotifications(true);
      await cubit.addReminder(const TimeOfDay(hour: 8, minute: 0));
      await cubit.updateReminder(0, const TimeOfDay(hour: 9, minute: 0));
      await cubit.removeReminder(0);

      expect(cubit.state.settings.notificationsEnabled, isTrue);
      expect(cubit.state.settings.reminders, isEmpty);
      expect(isarService.settings.reminders, isEmpty);
    },
  );

  test(
    'PDF export renderer mapping receives name saved through ProfileCubit',
    () async {
      final profileCubit = ProfileCubit.test(
        getOrCreateProfile: isarService.getOrCreateProfile,
        watchProfile: () => const Stream<UserProfile>.empty(),
        saveProfile: isarService.saveProfile,
        autoBind: false,
      );
      await profileCubit.updateProfile(name: 'Иван Петров', age: 19850410);

      isarService.records = [
        BloodPressureRecord()
          ..dateTime = DateTime(2026, 6, 18, 8)
          ..systolic = 120
          ..diastolic = 80
          ..pulse = 70,
      ];

      await cubit.exportData(ExportFormat.pdf);

      expect(exportService.capturedFields?.patientName, 'Иван Петров');
      expect(exportService.capturedFields?.age, '41');
      await profileCubit.close();
    },
  );

  test(
    'PDF export uses displayed profile name fallback when saved name is empty',
    () async {
      final profileCubit = ProfileCubit.test(
        getOrCreateProfile: isarService.getOrCreateProfile,
        watchProfile: () => const Stream<UserProfile>.empty(),
        saveProfile: isarService.saveProfile,
        autoBind: false,
      );
      await profileCubit.updateProfile(age: 19850410);

      isarService.records = [
        BloodPressureRecord()
          ..dateTime = DateTime(2026, 6, 18, 8)
          ..systolic = 120
          ..diastolic = 80
          ..pulse = 70,
      ];

      await cubit.exportData(ExportFormat.pdf);

      expect(exportService.capturedFields?.patientName, 'Дмитрий');
      expect(exportService.capturedFields?.age, '41');
      await profileCubit.close();
    },
  );
}

class _FakeIsarService implements IsarService {
  AppSettings settings = AppSettings();
  UserProfile profile = UserProfile();
  List<BloodPressureRecord> records = [];

  @override
  Future<AppSettings> getOrCreateSettings() async => settings.copyWith();

  @override
  Future<void> saveSettings(AppSettings settings) async {
    this.settings = settings.copyWith();
  }

  @override
  Future<UserProfile> getOrCreateProfile() async => profile;

  @override
  Future<void> saveProfile(UserProfile profile) async {
    this.profile = profile;
  }

  @override
  Future<List<BloodPressureRecord>> getAllRecords() async => records;

  @override
  Future<AppSettings?> getSettings() async => getOrCreateSettings();

  @override
  Future<UserProfile?> getProfile() async => getOrCreateProfile();

  @override
  Stream<AppSettings> watchSettings() => Stream.value(settings);

  @override
  Stream<UserProfile> watchProfile() => Stream.value(profile);

  @override
  Stream<List<BloodPressureRecord>> listenToRecords() => const Stream.empty();

  @override
  Future<void> saveRecord(BloodPressureRecord record) async {}

  @override
  Future<void> saveRecords(List<BloodPressureRecord> records) async {}

  @override
  Future<void> deleteRecord(int id) async {}

  @override
  Future<void> deleteAllRecords() async {}

  @override
  Future<void> replaceAllData({
    required AppSettings settings,
    required UserProfile profile,
    required List<BloodPressureRecord> records,
  }) async {
    this.settings = settings.copyWith();
    this.profile = profile;
  }
}

class _CapturingExportService extends ExportService {
  PdfProfileFields? capturedFields;

  @override
  Future<void> exportData(
    List<BloodPressureRecord> records,
    ExportFormat format,
    String languageCode, {
    UserProfile? profile,
    int periodDays = 14,
  }) async {
    capturedFields = pdfProfileFieldsForTest(profile, DateTime(2026, 6, 18));
  }
}

class _FakeNotificationService extends NotificationService {
  @override
  Future<void> scheduleDailyNotification(
    int id,
    TimeOfDay time, {
    String languageCode = 'ru',
  }) async {}

  @override
  Future<void> cancelNotification(int id) async {}
}

class _ThrowingNotificationService extends NotificationService {
  @override
  Future<void> scheduleDailyNotification(
    int id,
    TimeOfDay time, {
    String languageCode = 'ru',
  }) async {
    throw Exception('notification unavailable');
  }

  @override
  Future<void> cancelNotification(int id) async {
    throw Exception('notification unavailable');
  }
}
