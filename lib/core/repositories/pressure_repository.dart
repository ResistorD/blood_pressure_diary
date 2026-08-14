import '../database/isar_service.dart';
import '../../features/home/data/blood_pressure_model.dart';

/// ✅ Custom exception для валидации
class InvalidRecordException implements Exception {
  final String message;
  InvalidRecordException(this.message);

  @override
  String toString() => 'InvalidRecordException: $message';
}

class PressureRepository {
  final IsarService _isarService;
  List<BloodPressureRecord>? _cachedRecords;

  PressureRepository(this._isarService);

  void invalidateCache() {
    _cachedRecords = null;
  }

  Stream<List<BloodPressureRecord>> getAllRecordsStream() {
    return _isarService.listenToRecords();
  }

  /// ✅ Добавлена валидация перед сохранением
  Future<void> addRecord(BloodPressureRecord record) async {
    // Валидация систолического давления
    if (record.systolic < 60 || record.systolic > 300) {
      throw InvalidRecordException(
        'Systolic pressure must be between 60 and 300 mmHg (got: ${record.systolic})',
      );
    }

    // Валидация диастолического давления
    if (record.diastolic < 40 || record.diastolic > 200) {
      throw InvalidRecordException(
        'Diastolic pressure must be between 40 and 200 mmHg (got: ${record.diastolic})',
      );
    }

    // Валидация пульса
    if (record.pulse < 30 || record.pulse > 250) {
      throw InvalidRecordException(
        'Pulse must be between 30 and 250 bpm (got: ${record.pulse})',
      );
    }

    // Логическая проверка: систолическое должно быть больше диастолического
    if (record.systolic <= record.diastolic) {
      throw InvalidRecordException(
        'Systolic pressure (${record.systolic}) must be greater than diastolic (${record.diastolic})',
      );
    }

    await _isarService.saveRecord(record);
    invalidateCache();
  }

  /// ✅ Кэширование для оптимизации повторных чтений
  Future<List<BloodPressureRecord>> getAllRecords() async {
    if (_cachedRecords != null) return _cachedRecords!;
    _cachedRecords = await _isarService.getAllRecords();
    return _cachedRecords!;
  }

  Future<void> deleteRecord(int id) async {
    await _isarService.deleteRecord(id);
    invalidateCache();
  }

  Future<void> deleteAllRecords() async {
    await _isarService.deleteAllRecords();
    invalidateCache();
  }
}
