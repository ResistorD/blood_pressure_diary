import 'validation_policy.dart';

class ValidationUtils {
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
