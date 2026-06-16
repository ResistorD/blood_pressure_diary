import 'dart:io';

import 'package:csv/csv.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/services/backup_service.dart';
import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';

class CsvImportPreview {
  final List<BloodPressureRecord> records;
  final int skippedRows;

  const CsvImportPreview({required this.records, required this.skippedRows});
}

class SettingsFileActionException implements Exception {
  final String operation;
  final Object cause;

  const SettingsFileActionException(this.operation, this.cause);

  @override
  String toString() => 'SettingsFileActionException($operation): $cause';
}

class SettingsFileActions {
  final Future<String> Function() _createBackupJson;
  final Future<void> Function(String jsonText) _restoreFromJson;
  final Future<String?> Function() _pickBackupJsonPath;
  final Future<String?> Function() _pickCsvPath;
  final Future<String> Function(String path) _readFileText;
  final Future<void> Function(String path, String text) _writeFileText;
  final Future<void> Function(String path, String text) _shareFile;
  final Future<String> Function() _temporaryDirectoryPath;
  final Future<void> Function(List<BloodPressureRecord> records) _saveRecords;

  SettingsFileActions({
    required BackupService backupService,
    required IsarService isarService,
  }) : _createBackupJson = backupService.createBackupJson,
       _restoreFromJson = backupService.restoreFromJson,
       _pickBackupJsonPath = _pickJsonPathWithPicker,
       _pickCsvPath = _pickCsvPathWithPicker,
       _readFileText = _readFileTextFromDisk,
       _writeFileText = _writeFileTextToDisk,
       _shareFile = _shareFileWithPlatform,
       _temporaryDirectoryPath = _getTemporaryDirectoryPath,
       _saveRecords = isarService.saveRecords;

  @visibleForTesting
  SettingsFileActions.test({
    Future<String> Function()? createBackupJson,
    Future<void> Function(String jsonText)? restoreFromJson,
    Future<String?> Function()? pickBackupJsonPath,
    Future<String?> Function()? pickCsvPath,
    Future<String> Function(String path)? readFileText,
    Future<void> Function(String path, String text)? writeFileText,
    Future<void> Function(String path, String text)? shareFile,
    Future<String> Function()? temporaryDirectoryPath,
    Future<void> Function(List<BloodPressureRecord> records)? saveRecords,
  }) : _createBackupJson = createBackupJson ?? (() async => '{}'),
       _restoreFromJson = restoreFromJson ?? ((_) async {}),
       _pickBackupJsonPath = pickBackupJsonPath ?? (() async => null),
       _pickCsvPath = pickCsvPath ?? (() async => null),
       _readFileText = readFileText ?? _readFileTextFromDisk,
       _writeFileText = writeFileText ?? _writeFileTextToDisk,
       _shareFile = shareFile ?? _shareFileWithPlatform,
       _temporaryDirectoryPath =
           temporaryDirectoryPath ?? _getTemporaryDirectoryPath,
       _saveRecords = saveRecords ?? ((_) async {});

  static Future<String?> _pickJsonPathWithPicker() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['json'],
      withData: false,
    );
    if (result == null || result.files.isEmpty) return null;
    return result.files.first.path;
  }

  static Future<String?> _pickCsvPathWithPicker() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['csv'],
      withData: false,
    );
    if (result == null || result.files.isEmpty) return null;
    return result.files.first.path;
  }

  static Future<String> _readFileTextFromDisk(String path) {
    return File(path).readAsString();
  }

  static Future<void> _writeFileTextToDisk(String path, String text) {
    return File(path).writeAsString(text, flush: true);
  }

  static Future<void> _shareFileWithPlatform(String path, String text) async {
    await Share.shareXFiles([XFile(path)], text: text);
  }

  static Future<String> _getTemporaryDirectoryPath() async {
    final dir = await getTemporaryDirectory();
    return dir.path;
  }

  Future<T> _runFileAction<T>(
    String operation,
    Future<T> Function() action,
  ) async {
    try {
      return await action();
    } catch (e) {
      throw SettingsFileActionException(operation, e);
    }
  }

  Future<void> shareBackupJson({required String shareText}) {
    return _runFileAction('shareBackupJson', () async {
      final json = await _createBackupJson();
      final dirPath = await _temporaryDirectoryPath();
      final ts = DateTime.now().toIso8601String().replaceAll(':', '-');
      final path = '$dirPath/pressure_diary_backup_$ts.json';
      await _writeFileText(path, json);
      await _shareFile(path, shareText);
    });
  }

  Future<String?> pickBackupJsonPath() async {
    return _pickBackupJsonPath();
  }

  Future<void> restoreBackupFromPath(String path) {
    return _runFileAction('restoreBackupFromPath', () async {
      final jsonText = await _readFileText(path);
      await _restoreFromJson(jsonText);
    });
  }

  Future<CsvImportPreview?> pickAndParseCsv() async {
    final path = await _pickCsvPath();
    if (path == null) return null;

    return _runFileAction('pickAndParseCsv', () async {
      final csvText = await _readFileText(path);
      final rows = const CsvToListConverter(
        shouldParseNumbers: false,
      ).convert(csvText.replaceFirst('\ufeff', ''));
      final totalRows = rows.isEmpty ? 0 : rows.length - 1;
      final records = _parseMedMCsv(csvText);

      return CsvImportPreview(
        records: records,
        skippedRows: totalRows - records.length,
      );
    });
  }

  Future<void> importCsvRecords(List<BloodPressureRecord> records) {
    return _runFileAction('importCsvRecords', () async {
      await _saveRecords(records);
    });
  }

  int _csvColumnIndex(List<dynamic> header, List<String> names) {
    for (var i = 0; i < header.length; i++) {
      final value = header[i]
          .toString()
          .trim()
          .replaceAll('\ufeff', '')
          .toLowerCase();
      for (final name in names) {
        if (value == name.toLowerCase()) return i;
      }
    }
    return -1;
  }

  String _csvCell(List<dynamic> row, int index) {
    if (index < 0 || index >= row.length) return '';
    return row[index].toString().trim();
  }

  DateTime? _parseCsvDateTime(String date, String time) {
    final d = date.trim();
    final t = time.trim();
    if (d.isEmpty || t.isEmpty) return null;

    final dateFormats = <DateFormat>[
      DateFormat('yyyy-MM-dd'),
      DateFormat('dd.MM.yyyy'),
      DateFormat('dd/MM/yyyy'),
    ];

    DateTime? parsedDate;
    for (final format in dateFormats) {
      try {
        parsedDate = format.parseStrict(d);
        break;
      } catch (_) {
        // Try next format.
      }
    }
    if (parsedDate == null) return null;

    final timeParts = t.split(':');
    if (timeParts.length < 2) return null;
    final hour = int.tryParse(timeParts[0]);
    final minute = int.tryParse(timeParts[1]);
    if (hour == null || minute == null) return null;
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return null;

    return DateTime(
      parsedDate.year,
      parsedDate.month,
      parsedDate.day,
      hour,
      minute,
    );
  }

  List<BloodPressureRecord> _parseMedMCsv(String csvText) {
    final rows = const CsvToListConverter(
      shouldParseNumbers: false,
    ).convert(csvText.replaceFirst('\ufeff', ''));

    if (rows.isEmpty) return const <BloodPressureRecord>[];

    final header = rows.first;
    final dateIndex = _csvColumnIndex(header, ['Дата', 'Date']);
    final timeIndex = _csvColumnIndex(header, ['Время', 'Time']);
    final sysIndex = _csvColumnIndex(header, ['Сис', 'Systolic', 'SYS']);
    final diaIndex = _csvColumnIndex(header, ['Диа', 'Diastolic', 'DIA']);
    final pulseIndex = _csvColumnIndex(header, ['Пульс', 'Pulse']);
    final noteIndex = _csvColumnIndex(header, ['Заметка', 'Note']);

    if (dateIndex < 0 ||
        timeIndex < 0 ||
        sysIndex < 0 ||
        diaIndex < 0 ||
        pulseIndex < 0) {
      throw const FormatException('CSV columns not found');
    }

    final records = <BloodPressureRecord>[];

    for (final row in rows.skip(1)) {
      final dateTime = _parseCsvDateTime(
        _csvCell(row, dateIndex),
        _csvCell(row, timeIndex),
      );
      final systolic = int.tryParse(_csvCell(row, sysIndex));
      final diastolic = int.tryParse(_csvCell(row, diaIndex));
      final pulse = int.tryParse(_csvCell(row, pulseIndex));

      if (dateTime == null ||
          systolic == null ||
          diastolic == null ||
          pulse == null) {
        continue;
      }

      final note = _csvCell(row, noteIndex);

      records.add(
        BloodPressureRecord()
          ..dateTime = dateTime
          ..systolic = systolic
          ..diastolic = diastolic
          ..pulse = pulse
          ..note = note.isEmpty ? null : note
          ..tags = const [],
      );
    }

    return records;
  }
}
