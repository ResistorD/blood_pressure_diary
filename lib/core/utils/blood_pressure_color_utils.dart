import 'package:flutter/material.dart';
import '../theme/app_theme.dart';

class BloodPressureColorUtils {
  static Color getIndicatorColor(
      BuildContext context, {
        required int systolic,
        required int diastolic,
      }) {
    final c = context.appColors;

    final isLow = systolic < 100 || diastolic < 60;
    final isHigh = systolic >= 140 || diastolic >= 90;
    final isElevated = !isLow && !isHigh && (systolic >= 130 || diastolic >= 85);

    if (isHigh) return c.danger;
    if (isElevated) return c.warning;
    if (isLow) return AppPalette.blueAccent; // rgb(90,142,246)
    return c.success; // rgb(61,190,101)
  }
}
