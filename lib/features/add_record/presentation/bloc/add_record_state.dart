import 'package:equatable/equatable.dart';
import '../../../../core/utils/validation_policy.dart';
import '../../../../core/utils/validation_utils.dart';
import 'package:blood_pressure_diary/core/utils/input_field.dart';

class AddRecordState extends Equatable {
  final String systolic;
  final String diastolic;
  final String pulse;
  final String note;
  final DateTime selectedDateTime;
  final InputField activeField;
  final bool isSaved;
  final List<String> enabledKeys; // Поле для умной клавиатуры

  AddRecordState({
    this.systolic = '',
    this.diastolic = '',
    this.pulse = '',
    this.note = '',
    DateTime? selectedDateTime,
    this.activeField = InputField.systolic,
    this.isSaved = false,
    this.enabledKeys = const ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  }) : selectedDateTime = selectedDateTime ?? DateTime.now();

  /// Проверяет, валидна ли форма
  bool get isValid => ValidationUtils.isFormValid(
        systolic: systolic,
        diastolic: diastolic,
        pulse: pulse,
      );

  bool get systolicValid {
    final v = int.tryParse(systolic);
    if (v == null) return false;
    return v >= ValidationPolicy.minSys && v <= ValidationPolicy.maxSys;
  }

  bool get diastolicValid {
    final d = int.tryParse(diastolic);
    if (d == null) return false;

    final s = int.tryParse(systolic);
    if (s == null) {
      return d >= ValidationPolicy.minDia &&
          d <= ValidationPolicy.maxDia;
    }

    final (min, max) = ValidationUtils.diaRangeForSys(s);

    return d >= min && d <= max;
  }



  bool get pulseValid {
    final p = int.tryParse(pulse);
    if (p == null) return false;
    return p >= ValidationPolicy.minPulse && p <= ValidationPolicy.maxPulse;
  }

  AddRecordState copyWith({
    String? systolic,
    String? diastolic,
    String? pulse,
    String? note,
    DateTime? selectedDateTime,
    InputField? activeField,
    bool? isSaved,
    List<String>? enabledKeys,
  }) {
    return AddRecordState(
      systolic: systolic ?? this.systolic,
      diastolic: diastolic ?? this.diastolic,
      pulse: pulse ?? this.pulse,
      note: note ?? this.note,
      selectedDateTime: selectedDateTime ?? this.selectedDateTime,
      activeField: activeField ?? this.activeField,
      isSaved: isSaved ?? this.isSaved,
      enabledKeys: enabledKeys ?? this.enabledKeys,
    );
  }

  @override
  List<Object?> get props => [
    systolic,
    diastolic,
    pulse,
    note,
    selectedDateTime,
    activeField,
    isSaved,
    enabledKeys,
  ];
}
