import 'dart:convert';

import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';
import 'package:blood_pressure_diary/features/settings/data/models/settings_model.dart';

class BackupService {
  final IsarService _isar;

  BackupService(this._isar);

  static const int backupVersion = 1;

  Future<String> createBackupJson() async {
    final settings = await _isar.getSettings() ?? AppSettings();
    final profile = await _isar.getProfile() ?? UserProfile();
    final records = await _isar.getAllRecords();

    final map = <String, dynamic>{
      'version': backupVersion,
      'createdAt': DateTime.now().toUtc().toIso8601String(),
      'settings': _settingsToMap(settings),
      'profile': _profileToMap(profile),
      'records': records.map(_recordToMap).toList(growable: false),
    };

    return const JsonEncoder.withIndent('  ').convert(map);
    // (Indent полезен: файл читаемый, проще отлаживать. При желании можно убрать.)
  }

  Future<void> restoreFromJson(String jsonText) async {
    final dynamic decoded = jsonDecode(jsonText);
    if (decoded is! Map<String, dynamic>) {
      throw const FormatException('Backup JSON is not an object');
    }

    final version = decoded['version'];
    if (version != backupVersion) {
      throw FormatException('Unsupported backup version: $version');
    }

    final settingsMap = decoded['settings'];
    final profileMap = decoded['profile'];
    final recordsList = decoded['records'];

    if (settingsMap is! Map<String, dynamic>) {
      throw const FormatException('Backup JSON: "settings" is invalid');
    }
    if (profileMap is! Map<String, dynamic>) {
      throw const FormatException('Backup JSON: "profile" is invalid');
    }
    if (recordsList is! List) {
      throw const FormatException('Backup JSON: "records" is invalid');
    }

    final settings = _settingsFromMap(settingsMap);
    final profile = _profileFromMap(profileMap);

    final records = <BloodPressureRecord>[];
    for (final item in recordsList) {
      if (item is! Map<String, dynamic>) continue;
      records.add(_recordFromMap(item));
    }

    // Восстановление: перезаписываем (settings/profile) и полностью заменяем записи давления.
    await _isar.replaceAllData(
      settings: settings,
      profile: profile,
      records: records,
    );
  }

  // -------------------- MAPPERS --------------------

  Map<String, dynamic> _settingsToMap(AppSettings s) => <String, dynamic>{
    'themeMode': s.themeMode.name, // light/dark/system
    'languageCode': s.languageCode,
    'reminders': s.reminders,
    'notificationsEnabled': s.notificationsEnabled,
    'accountLinked': s.accountLinked,
    'accountEmail': s.accountEmail,
    'accountProvider': s.accountProvider,
  };

  AppSettings _settingsFromMap(Map<String, dynamic> m) {
    final themeStr = (m['themeMode'] ?? 'light').toString();
    final theme = AppThemeMode.values.firstWhere(
          (e) => e.name == themeStr,
      orElse: () => AppThemeMode.light,
    );

    final remindersRaw = m['reminders'];
    final reminders = (remindersRaw is List)
        ? remindersRaw.map((e) => e.toString()).toList(growable: false)
        : <String>[];

    return AppSettings(
      themeMode: theme,
      languageCode: (m['languageCode'] ?? 'ru').toString(),
      reminders: reminders,
      notificationsEnabled: m['notificationsEnabled'] == true,
      accountLinked: m['accountLinked'] == true,
      accountEmail: (m['accountEmail'] ?? '').toString(),
      accountProvider: (m['accountProvider'] ?? '').toString(),
    )..id = 0;
  }

  Map<String, dynamic> _profileToMap(UserProfile p) => <String, dynamic>{
    'name': p.name,
    'age': p.age,
    'gender': p.gender,
    'weight': p.weight,
    'targetSystolic': p.targetSystolic,
    'targetDiastolic': p.targetDiastolic,
  };

  UserProfile _profileFromMap(Map<String, dynamic> m) {
    return UserProfile(
      name: (m['name'] ?? '').toString(),
      age: (m['age'] is num) ? (m['age'] as num).toInt() : 0,
      gender: (m['gender'] ?? 'male').toString(),
      weight: (m['weight'] is num) ? (m['weight'] as num).toDouble() : 0.0,
      targetSystolic: (m['targetSystolic'] is num) ? (m['targetSystolic'] as num).toInt() : 120,
      targetDiastolic: (m['targetDiastolic'] is num) ? (m['targetDiastolic'] as num).toInt() : 80,
    )..id = 0;
  }

  Map<String, dynamic> _recordToMap(BloodPressureRecord r) => <String, dynamic>{
    'dateTime': r.dateTime.toUtc().toIso8601String(),
    'systolic': r.systolic,
    'diastolic': r.diastolic,
    'pulse': r.pulse,
    'note': r.note,
    'emotion': r.emotion,
  };

  BloodPressureRecord _recordFromMap(Map<String, dynamic> m) {
    final dtStr = (m['dateTime'] ?? '').toString();
    final dt = DateTime.tryParse(dtStr)?.toLocal() ?? DateTime.now();

    final r = BloodPressureRecord()
      ..dateTime = dt
      ..systolic = (m['systolic'] is num) ? (m['systolic'] as num).toInt() : 0
      ..diastolic = (m['diastolic'] is num) ? (m['diastolic'] as num).toInt() : 0
      ..pulse = (m['pulse'] is num) ? (m['pulse'] as num).toInt() : 0
      ..note = m['note']?.toString()
      ..emotion = m['emotion']?.toString();

    // id не переносим — Isar сам выдаст новые id.
    return r;
  }
}
