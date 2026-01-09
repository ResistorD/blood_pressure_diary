import 'package:blood_pressure_diary/core/utils/input_field.dart';
import 'package:blood_pressure_diary/core/utils/validation_policy.dart';
import 'package:blood_pressure_diary/core/utils/validation_utils.dart';

class SmartInputEngine {
  /// Определяет целевую длину поля на основе первой введенной цифры.
  static int getTargetLength(InputField field, String currentText, String nextDigit) {
    assert(currentText.isNotEmpty || nextDigit.isNotEmpty);
    final first = currentText.isEmpty ? nextDigit : currentText[0];
    return _targetLenByFirstDigit(field: field, firstDigit: first);
  }

  /// Проверяет, можно ли добавить цифру к текущему тексту.
  static bool isDigitAllowed({
    required InputField field,
    required String currentText,
    required String digit,
    int? systolicValue,
  }) {
    if (digit.length != 1) return false;
    final code = digit.codeUnitAt(0);
    if (code < 48 || code > 57) return false;

    // Ведущий ноль запрещен
    if (currentText.isEmpty && digit == '0') return false;

    final newText = currentText + digit;
    final targetLen = getTargetLength(field, currentText, digit);

    // Если превышаем длину — запрещено
    if (newText.length > targetLen) return false;

    // Если это финальная длина — проверяем диапазон
    if (newText.length == targetLen) {
      final value = int.tryParse(newText) ?? 0;
      return _isInRange(field, value, systolicValue);
    }

    // Если это промежуточный ввод — проверяем, достижим ли хоть один валидный результат
    return _isReachable(field, newText, targetLen, systolicValue);
  }

  /// Нужно ли автоматически переходить к следующему полю.
  static bool shouldAutoAdvance({
    required InputField field,
    required String currentText,
    int? systolicValue,
  }) {
    if (currentText.isEmpty) return false;

    final targetLen = _targetLenByFirstDigit(field: field, firstDigit: currentText[0]);
    if (currentText.length >= targetLen) return true;

    for (int i = 0; i <= 9; i++) {
      if (isDigitAllowed(
        field: field,
        currentText: currentText,
        digit: i.toString(),
        systolicValue: systolicValue,
      )) {
        return false;
      }
    }
    return true;
  }

  static bool _isInRange(InputField field, int value, int? systolicValue) {
    return switch (field) {
      InputField.systolic =>
      value >= ValidationPolicy.minSys && value <= ValidationPolicy.maxSys,
      InputField.diastolic => _isDiaInRange(value, systolicValue),
      InputField.pulse =>
      value >= ValidationPolicy.minPulse && value <= ValidationPolicy.maxPulse,
      _ => true,
    };
  }

  static bool _isDiaInRange(int value, int? systolicValue) {
    if (systolicValue == null) {
      return value >= ValidationPolicy.minDia && value <= ValidationPolicy.maxDia;
    }
    final (min, max) = ValidationUtils.diaRangeForSys(systolicValue);
    return value >= min && value <= max;
  }

  static bool _isReachable(
      InputField field,
      String prefix,
      int targetLen,
      int? systolicValue,
      ) {
    final diff = targetLen - prefix.length;
    if (diff <= 0) return _isInRange(field, int.parse(prefix), systolicValue);

    final minPossible = int.parse(prefix + ('0' * diff));
    final maxPossible = int.parse(prefix + ('9' * diff));

    return switch (field) {
      InputField.systolic =>
      !(maxPossible < ValidationPolicy.minSys || minPossible > ValidationPolicy.maxSys),
      InputField.diastolic => _isDiaReachable(minPossible, maxPossible, systolicValue),
      InputField.pulse =>
      !(maxPossible < ValidationPolicy.minPulse || minPossible > ValidationPolicy.maxPulse),
      _ => true,
    };
  }

  static bool _isDiaReachable(int minPossible, int maxPossible, int? systolicValue) {
    int minAllowed = ValidationPolicy.minDia;
    int maxAllowed = ValidationPolicy.maxDia;

    if (systolicValue != null) {
      final (min, max) = ValidationUtils.diaRangeForSys(systolicValue);
      minAllowed = min;
      maxAllowed = max;
    }

    return !(maxPossible < minAllowed || minPossible > maxAllowed);
  }

  static int _targetLenByFirstDigit({
    required InputField field,
    required String firstDigit,
  }) {
    return switch (field) {
      InputField.systolic => (firstDigit == '1' || firstDigit == '2') ? 3 : 2,
      InputField.diastolic => (firstDigit == '1') ? 3 : 2,
      InputField.pulse => (firstDigit == '1' || firstDigit == '2') ? 3 : 2,
      _ => 3,
    };
  }

}
