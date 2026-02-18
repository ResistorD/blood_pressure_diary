import 'validation_policy.dart';

class ValidationUtils {
  // UI-хелперы для подсветки и подсказок в AddRecordScreen.
  // Используем те же правила, что и финальная валидация формы.
  static bool isSystolicValid(String value) {
    final sys = int.tryParse(value.trim());
    if (sys == null) return false;
    return sys >= ValidationPolicy.minSys && sys <= ValidationPolicy.maxSys;
  }

  static bool isPulseValid(String value) {
    final pul = int.tryParse(value.trim());
    if (pul == null) return false;
    return pul >= ValidationPolicy.minPulse && pul <= ValidationPolicy.maxPulse;
  }

  static bool isDiastolicValid(String diastolicValue, {String? systolicValue}) {
    final dia = int.tryParse(diastolicValue.trim());
    if (dia == null) return false;

    final sys = systolicValue == null ? null : int.tryParse(systolicValue.trim());
    if (sys == null) {
      // Без SYS можем проверить только общий диапазон.
      return dia >= ValidationPolicy.minDia && dia <= ValidationPolicy.maxDia;
    }

    final (diaMin, diaMax) = diaRangeForSys(sys);
    return dia >= diaMin && dia <= diaMax;
  }

  /// Проверка финальной валидности всей формы.
  static bool isFormValid({
    required String systolic,
    required String diastolic,
    required String pulse,
  }) {
    final sys = int.tryParse(systolic);
    final dia = int.tryParse(diastolic);
    final pul = int.tryParse(pulse);

    if (sys == null || dia == null || pul == null) return false;

    if (sys < ValidationPolicy.minSys || sys > ValidationPolicy.maxSys) return false;
    if (pul < ValidationPolicy.minPulse || pul > ValidationPolicy.maxPulse) return false;

    final (diaMin, diaMax) = diaRangeForSys(sys);
    if (dia < diaMin || dia > diaMax) return false;

    return true;
  }

  /// Допустимый диапазон DIA зависит от текущего SYS.
  static (int, int) diaRangeForSys(int sys) {
    final lo = (sys - ValidationPolicy.maxSysDiaDiff) > ValidationPolicy.minDia
        ? (sys - ValidationPolicy.maxSysDiaDiff)
        : ValidationPolicy.minDia;

    final hi = (sys - 1) < ValidationPolicy.maxDia
        ? (sys - 1)
        : ValidationPolicy.maxDia;

    return (lo, hi);
  }
}
