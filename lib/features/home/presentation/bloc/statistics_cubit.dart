import 'package:flutter_bloc/flutter_bloc.dart';
import '../../data/blood_pressure_model.dart';
import 'statistics_state.dart';

class StatisticsCubit extends Cubit<StatisticsState> {
  List<BloodPressureRecord> _allRecords;

  StatisticsCubit(
      List<BloodPressureRecord> records, {
        int targetSystolic = 120,
        int targetDiastolic = 80,
      })  : _allRecords = List<BloodPressureRecord>.from(records),
        super(StatisticsState(
        targetSystolic: targetSystolic,
        targetDiastolic: targetDiastolic,
      )) {
    updatePeriod(StatisticsPeriod.sevenDays);
  }

  /// ✅ Обновить исходные записи (например, после удаления/добавления в журнале)
  /// и пересчитать текущий период без перезапуска приложения.
  void updateRecords(List<BloodPressureRecord> records) {
    _allRecords = List<BloodPressureRecord>.from(records);
    updatePeriod(state.period);
  }

  void updatePeriod(StatisticsPeriod period) {
    final now = DateTime.now();
    List<BloodPressureRecord> filtered;

    switch (period) {
      case StatisticsPeriod.sevenDays:
        filtered = _allRecords
            .where((r) => r.dateTime.isAfter(now.subtract(const Duration(days: 7))))
            .toList();
        break;
      case StatisticsPeriod.thirtyDays:
        filtered = _allRecords
            .where((r) => r.dateTime.isAfter(now.subtract(const Duration(days: 30))))
            .toList();
        break;
      case StatisticsPeriod.all:
        filtered = List.from(_allRecords);
        break;
    }

    filtered.sort((a, b) => a.dateTime.compareTo(b.dateTime));

    // Thinning if records > 100
    if (filtered.length > 100) {
      final int skip = (filtered.length / 50).floor();
      final List<BloodPressureRecord> thinned = [];
      for (int i = 0; i < filtered.length; i++) {
        if (skip <= 1 || i % skip == 0 || i == filtered.length - 1) {
          thinned.add(filtered[i]);
        }
      }
      filtered = thinned;
    }

    _calculateAnalytics(filtered, period);
  }

  void _calculateAnalytics(List<BloodPressureRecord> records, StatisticsPeriod period) {
    if (records.isEmpty) {
      emit(state.copyWith(
        filteredRecords: const [],
        period: period,
        maxSys: 0,
        maxDia: 0,
        minSys: 0,
        minDia: 0,
        avgSys: 0,
        avgDia: 0,
        maxPulse: 0,
        minPulse: 0,
        avgPulse: 0,
      ));
      return;
    }

    double maxSys = 0;
    double maxDia = 0;
    double minSys = double.infinity;
    double minDia = double.infinity;
    double sumSys = 0;
    double sumDia = 0;

    // pulse analytics ignore invalid (<=0)
    double maxPulse = 0;
    double minPulse = double.infinity;
    double sumPulse = 0;
    int pulseCount = 0;

    for (final r in records) {
      if (r.systolic > maxSys) maxSys = r.systolic.toDouble();
      if (r.diastolic > maxDia) maxDia = r.diastolic.toDouble();
      if (r.systolic < minSys) minSys = r.systolic.toDouble();
      if (r.diastolic < minDia) minDia = r.diastolic.toDouble();
      sumSys += r.systolic;
      sumDia += r.diastolic;

      final p = r.pulse;
      if (p > 0) {
        if (p > maxPulse) maxPulse = p.toDouble();
        if (p < minPulse) minPulse = p.toDouble();
        sumPulse += p;
        pulseCount++;
      }
    }

    emit(state.copyWith(
      filteredRecords: records,
      period: period,
      maxSys: maxSys,
      maxDia: maxDia,
      minSys: minSys == double.infinity ? 0 : minSys,
      minDia: minDia == double.infinity ? 0 : minDia,
      avgSys: sumSys / records.length,
      avgDia: sumDia / records.length,
      maxPulse: maxPulse,
      minPulse: minPulse == double.infinity ? 0 : minPulse,
      avgPulse: pulseCount == 0 ? 0 : (sumPulse / pulseCount),
    ));
  }
}
