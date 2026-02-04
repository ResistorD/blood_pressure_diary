import 'package:flutter/material.dart';
import 'package:isar/isar.dart';

import 'package:blood_pressure_diary/core/utils/pressure_assessment_policy.dart';

part 'blood_pressure_model.g.dart';

@Collection()
class BloodPressureRecord {
  Id id = Isar.autoIncrement;

  @Index()
  late DateTime dateTime;
  late int systolic;
  late int diastolic;
  late int pulse;

  String? note;    // Поле для заметок (бывший comment)
  String? emotion; // Твой эмодзи
  List<String> tags = const []; // Контекстные теги (после кофе, стресс и т.п.)

  @ignore
  Color get statusColor {
    final category = PressureAssessmentPolicy.assess(systolic, diastolic);
    switch (category) {
      case PressureCategory.low:
        return const Color(0xFF60A5FA); // голубой
      case PressureCategory.normal:
        return const Color(0xFF22C55E); // зелёный
      case PressureCategory.elevated:
        return const Color(0xFFFACC15); // желтый
      case PressureCategory.high1:
      case PressureCategory.high2:
      case PressureCategory.crisis:
        return const Color(0xFFE11D48); // красный
    }
  }

  @ignore
  String get statusText {
    final category = PressureAssessmentPolicy.assess(systolic, diastolic);
    switch (category) {
      case PressureCategory.low:
        return 'Понижено';
      case PressureCategory.normal:
        return 'Норма';
      case PressureCategory.elevated:
        return 'Повышено';
      case PressureCategory.high1:
        return 'Гипертония 1';
      case PressureCategory.high2:
        return 'Гипертония 2';
      case PressureCategory.crisis:
        return 'Кризис';
    }
  }
}
