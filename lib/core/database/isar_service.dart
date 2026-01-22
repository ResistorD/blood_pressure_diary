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
    return await _isar.bloodPressureRecords
        .where()
        .sortByDateTimeDesc()
        .findAll();
  }

  Future<void> saveRecord(BloodPressureRecord record) async {
    await _isar.writeTxn(() async {
      await _isar.bloodPressureRecords.put(record);
    });
  }

  Future<void> saveRecords(List<BloodPressureRecord> records) async {
    await _isar.writeTxn(() async {
      await _isar.bloodPressureRecords.putAll(records);
    });
  }

  Future<void> deleteRecord(int id) async {
    await _isar.writeTxn(() async {
      await _isar.bloodPressureRecords.delete(id);
    });
  }

  Future<void> deleteAllRecords() async {
    await _isar.writeTxn(() async {
      await _isar.bloodPressureRecords.clear();
    });
  }

  // --- Settings ---
  Future<AppSettings?> getSettings() async {
    return await _isar.appSettings.get(0);
  }

  Future<void> saveSettings(AppSettings settings) async {
    await _isar.writeTxn(() async {
      settings.id = 0;
      await _isar.appSettings.put(settings);
    });
  }

  // --- Profile ---
  Future<UserProfile?> getProfile() async {
    return await _isar.userProfiles.get(0);
  }

  Future<void> saveProfile(UserProfile profile) async {
    await _isar.writeTxn(() async {
      profile.id = 0;
      await _isar.userProfiles.put(profile);
    });
  }

  /// Полная замена данных приложения (для restore):
  /// - settings/profile перезаписываем
  /// - записи давления полностью заменяем
  Future<void> replaceAllData({
    required AppSettings settings,
    required UserProfile profile,
    required List<BloodPressureRecord> records,
  }) async {
    await _isar.writeTxn(() async {
      settings.id = 0;
      profile.id = 0;

      await _isar.appSettings.put(settings);
      await _isar.userProfiles.put(profile);

      await _isar.bloodPressureRecords.clear();
      await _isar.bloodPressureRecords.putAll(records);
    });
  }
}
