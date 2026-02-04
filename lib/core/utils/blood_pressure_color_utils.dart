import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class BloodPressureColorUtils {
  /// Цвет маркера записи в журнале.
  /// Логика синхронизирована с зонами на графике:
  /// SYS: target ±10, DIA: target ±5.
  static Color getIndicatorColor(
      BuildContext context, {
        required int systolic,
        required int diastolic,
        required int targetSystolic,
        required int targetDiastolic,
      }) {
    final c = context.appColors;

    const sysDelta = 10;
    const diaDelta = 5;

    final sysLow = targetSystolic - sysDelta;
    final sysHigh = targetSystolic + sysDelta;
    final diaLow = targetDiastolic - diaDelta;
    final diaHigh = targetDiastolic + diaDelta;

    final isLow = systolic < sysLow || diastolic < diaLow;
    final isHigh = systolic > sysHigh || diastolic > diaHigh;

    if (isHigh) return c.danger;
    if (isLow) return AppPalette.blueAccent; // низкое давление
    return c.success; // в зоне
  }
}