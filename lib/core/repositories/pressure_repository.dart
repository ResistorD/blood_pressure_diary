import '../database/isar_service.dart';
import '../../features/home/data/blood_pressure_model.dart';

class PressureRepository {
  final IsarService _isarService;

  PressureRepository(this._isarService);

  Stream<List<BloodPressureRecord>> getAllRecordsStream() {
    return _isarService.listenToRecords();
  }

  Future<void> addRecord(BloodPressureRecord record) async {
    await _isarService.saveRecord(record);
  }

  Future<List<BloodPressureRecord>> getAllRecords() async {
    return await _isarService.getAllRecords();
  }

  Future<void> deleteRecord(int id) async {
    await _isarService.deleteRecord(id);
  }

  Future<void> deleteAllRecords() async {
    await _isarService.deleteAllRecords();
  }
}
