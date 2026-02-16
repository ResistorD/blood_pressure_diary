import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:isar/isar.dart';

import '../../features/home/data/blood_pressure_model.dart';
import '../../features/settings/data/models/settings_model.dart';
import '../database/models/user_profile.dart';

class IsarService {
  final Isar _isar;

  IsarService(this._isar);

  // --- Records ---
  Stream<List<BloodPressureRecord>> listenToRecords() {
    return _isar.bloodPressureRecords
        .where()
        .sortByDateTimeDesc()
        .watch(fireImmediately: true);
  }

  Future<List<BloodPressureRecord>> getAllRecords() async {
    return await _isar.bloodPressureRecords.where().sortByDateTimeDesc().findAll();
  }

  Future<void> saveRecord(BloodPressureRecord record) async {
    try {
      await _isar.writeTxn(() async {
        await _isar.bloodPressureRecords.put(record);
      });
    } on IsarError catch (e) {
      debugPrint('IsarService.saveRecord error: $e');
      throw Exception('Failed to save record: $e');
    }
  }

  Future<void> saveRecords(List<BloodPressureRecord> records) async {
    try {
      await _isar.writeTxn(() async {
        await _isar.bloodPressureRecords.putAll(records);
      });
    } on IsarError catch (e) {
      debugPrint('IsarService.saveRecords error: $e');
      throw Exception('Failed to save records: $e');
    }
  }

  Future<void> deleteRecord(int id) async {
    try {
      await _isar.writeTxn(() async {
        await _isar.bloodPressureRecords.delete(id);
      });
    } on IsarError catch (e) {
      debugPrint('IsarService.deleteRecord error: $e');
      throw Exception('Failed to delete record: $e');
    }
  }

  Future<void> deleteAllRecords() async {
    try {
      await _isar.writeTxn(() async {
        await _isar.bloodPressureRecords.clear();
      });
    } on IsarError catch (e) {
      debugPrint('IsarService.deleteAllRecords error: $e');
      throw Exception('Failed to delete all records: $e');
    }
  }

  // --- Settings (singleton, id=0) ---

  /// Реактивное наблюдение за singleton-настройками (id=0).
  /// Важно: запись должна существовать (создаётся через [getOrCreateSettings]).
  Stream<AppSettings> watchSettings() {
    return _isar.appSettings
        .watchObject(0, fireImmediately: true)
        .where((s) => s != null)
        .cast<AppSettings>();
  }

  Future<AppSettings> getOrCreateSettings() async {
    final byId = await _isar.appSettings.get(0);
    if (byId != null) return byId;

    // Если в базе есть "какая-то" запись настроек (после старых экспериментов),
    // поднимаем её и насильно делаем singleton id=0.
    final any = await _isar.appSettings.where().findFirst();
    if (any != null) {
      any.id = 0;
      await _isar.writeTxn(() async {
        await _isar.appSettings.put(any);
      });
      return any;
    }

    final created = AppSettings()..id = 0;
    await _isar.writeTxn(() async {
      await _isar.appSettings.put(created);
    });
    return created;
  }

  Future<AppSettings?> getSettings() async {
    return await getOrCreateSettings();
  }

  Future<void> saveSettings(AppSettings settings) async {
    try {
      await _isar.writeTxn(() async {
        settings.id = 0;
        await _isar.appSettings.put(settings);
      });
    } on IsarError catch (e) {
      debugPrint('IsarService.saveSettings error: $e');
      throw Exception('Failed to save settings: $e');
    }
  }

  // --- Profile (singleton, id=0) ---

  /// Реактивное наблюдение за singleton-профилем (id=0).
  /// Важно: запись должна существовать (создаётся через [getOrCreateProfile]).
  Stream<UserProfile> watchProfile() {
    return _isar.userProfiles
        .watchObject(0, fireImmediately: true)
        .where((p) => p != null)
        .cast<UserProfile>();
  }

  Future<UserProfile> getOrCreateProfile() async {
    final byId = await _isar.userProfiles.get(0);
    if (byId != null) return byId;

    final any = await _isar.userProfiles.where().findFirst();
    if (any != null) {
      any.id = 0;
      await _isar.writeTxn(() async {
        await _isar.userProfiles.put(any);
      });
      return any;
    }

    final created = UserProfile()..id = 0;
    await _isar.writeTxn(() async {
      await _isar.userProfiles.put(created);
    });
    return created;
  }

  Future<UserProfile?> getProfile() async {
    return await getOrCreateProfile();
  }

  Future<void> saveProfile(UserProfile profile) async {
    try {
      await _isar.writeTxn(() async {
        profile.id = 0;
        await _isar.userProfiles.put(profile);
      });
    } on IsarError catch (e) {
      debugPrint('IsarService.saveProfile error: $e');
      throw Exception('Failed to save profile: $e');
    }
  }

  /// Полная замена данных приложения (для restore):
  /// - settings/profile перезаписываем
  /// - записи давления полностью заменяем
  Future<void> replaceAllData({
    required AppSettings settings,
    required UserProfile profile,
    required List<BloodPressureRecord> records,
  }) async {
    try {
      await _isar.writeTxn(() async {
        settings.id = 0;
        profile.id = 0;

        await _isar.appSettings.put(settings);
        await _isar.userProfiles.put(profile);

        await _isar.bloodPressureRecords.clear();
        await _isar.bloodPressureRecords.putAll(records);
      });
    } on IsarError catch (e) {
      debugPrint('IsarService.replaceAllData error: $e');
      throw Exception('Failed to restore backup: $e');
    }
  }
}
