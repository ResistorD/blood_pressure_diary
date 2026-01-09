enum PressureCategory {
  low,
  normal,
  elevated,
  high1,
  high2,
  crisis
}

class PressureAssessmentPolicy {
  /// Оценивает состояние на основе систолического и диастолического давления.
  /// Логика основана на стандартных медицинских рекомендациях, но может быть расширена.
  static PressureCategory assess(int systolic, int diastolic) {
    if (systolic >= 180 || diastolic >= 120) return PressureCategory.crisis;
    if (systolic >= 160 || diastolic >= 100) return PressureCategory.high2;
    if (systolic >= 140 || diastolic >= 90) return PressureCategory.high1;
    if (systolic >= 130 || diastolic >= 80) return PressureCategory.elevated;
    if (systolic < 90 || diastolic < 60) return PressureCategory.low;
    return PressureCategory.normal;
  }

  static bool isHigh(int systolic, int diastolic) {
    final category = assess(systolic, diastolic);
    return category == PressureCategory.high1 || 
           category == PressureCategory.high2 || 
           category == PressureCategory.crisis;
  }

  static bool isLow(int systolic, int diastolic) {
    return assess(systolic, diastolic) == PressureCategory.low;
  }
}
