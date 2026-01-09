import 'package:flutter/material.dart';

/// Утилиты для определения цвета индикатора давления
class BloodPressureColorUtils {
  /// Определяет цвет индикатора на основе систолического давления
  /// Используется для визуального отображения состояния давления в списке
  static Color getIndicatorColor(int systolic) {
    if (systolic < 120) return Colors.green;
    if (systolic < 140) return Colors.orange;
    return Colors.red;
  }
}
