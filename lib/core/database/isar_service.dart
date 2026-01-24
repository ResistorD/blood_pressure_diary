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

  // --- Settings (singleton, id=0) ---
  Future<AppSettings> getOrCreateSettings() async {
    final byId = await _isar.appSettings.get(0);
    if (byId != null) return byId;

    // Если в базе есть "какая-то" запись настроек (например после старых экспериментов),
    // поднимаем её и насильно делаем singleton id=0.
    final any = await _isar.appSettings.where().findFirst();
    if (any != null) {
      any.id = 0;
      await _isar.writeTxn(() async {
        await _isar.appSettings.clear();
        await _isar.appSettings.put(any);
      });
      return any;
    }

    // Совсем пусто — создаём дефолт и сохраняем.
    final created = AppSettings()..id = 0;
    await _isar.writeTxn(() async {
      await _isar.appSettings.clear();
      await _isar.appSettings.put(created);
    });
    return created;
  }

  Future<AppSettings?> getSettings() async {
    // оставляю метод, но делаю его надёжным
    return await getOrCreateSettings();
  }

  Future<void> saveSettings(AppSettings settings) async {
    await _isar.writeTxn(() async {
      settings.id = 0;
      // гарантируем, что в коллекции всегда 1 запись
      await _isar.appSettings.clear();
      await _isar.appSettings.put(settings);
    });
  }

  // --- Profile (singleton, id=0) ---
  Future<UserProfile> getOrCreateProfile() async {
    final byId = await _isar.userProfiles.get(0);
    if (byId != null) return byId;

    final any = await _isar.userProfiles.where().findFirst();
    if (any != null) {
      any.id = 0;
      await _isar.writeTxn(() async {
        await _isar.userProfiles.clear();
        await _isar.userProfiles.put(any);
      });
      return any;
    }

    final created = UserProfile()..id = 0;
    await _isar.writeTxn(() async {
      await _isar.userProfiles.clear();
      await _isar.userProfiles.put(created);
    });
    return created;
  }

  Future<UserProfile?> getProfile() async {
    return await getOrCreateProfile();
  }

  Future<void> saveProfile(UserProfile profile) async {
    await _isar.writeTxn(() async {
      profile.id = 0;
      await _isar.userProfiles.clear();
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

      await _isar.appSettings.clear();
      await _isar.userProfiles.clear();

      await _isar.appSettings.put(settings);
      await _isar.userProfiles.put(profile);

      await _isar.bloodPressureRecords.clear();
      await _isar.bloodPressureRecords.putAll(records);
    });
  }
}
