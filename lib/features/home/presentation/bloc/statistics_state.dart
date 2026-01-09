import 'package:equatable/equatable.dart';
import '../../data/blood_pressure_model.dart';

enum StatisticsPeriod { sevenDays, thirtyDays, all }

class StatisticsState extends Equatable {
  final List<BloodPressureRecord> filteredRecords;
  final StatisticsPeriod period;
  final double maxSys;
  final double maxDia;
  final double minSys;
  final double minDia;
  final double avgSys;
  final double avgDia;
  final int targetSystolic;
  final int targetDiastolic;

  const StatisticsState({
    this.filteredRecords = const [],
    this.period = StatisticsPeriod.sevenDays,
    this.maxSys = 0,
    this.maxDia = 0,
    this.minSys = 0,
    this.minDia = 0,
    this.avgSys = 0,
    this.avgDia = 0,
    this.targetSystolic = 120,
    this.targetDiastolic = 80,
  });

  StatisticsState copyWith({
    List<BloodPressureRecord>? filteredRecords,
    StatisticsPeriod? period,
    double? maxSys,
    double? maxDia,
    double? minSys,
    double? minDia,
    double? avgSys,
    double? avgDia,
    int? targetSystolic,
    int? targetDiastolic,
  }) {
    return StatisticsState(
      filteredRecords: filteredRecords ?? this.filteredRecords,
      period: period ?? this.period,
      maxSys: maxSys ?? this.maxSys,
      maxDia: maxDia ?? this.maxDia,
      minSys: minSys ?? this.minSys,
      minDia: minDia ?? this.minDia,
      avgSys: avgSys ?? this.avgSys,
      avgDia: avgDia ?? this.avgDia,
      targetSystolic: targetSystolic ?? this.targetSystolic,
      targetDiastolic: targetDiastolic ?? this.targetDiastolic,
    );
  }

  @override
  List<Object?> get props => [
        filteredRecords,
        period,
        maxSys,
        maxDia,
        minSys,
        minDia,
        avgSys,
        avgDia,
        targetSystolic,
        targetDiastolic,
      ];
}
