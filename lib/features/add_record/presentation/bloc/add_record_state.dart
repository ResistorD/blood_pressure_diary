import 'package:equatable/equatable.dart';

import 'package:blood_pressure_diary/core/utils/input_field.dart';
import '../../../../core/utils/validation_utils.dart';

class AddRecordState extends Equatable {
  final String systolic;
  final String diastolic;
  final String pulse;
  final String note;

  final DateTime selectedDateTime;
  final InputField activeField;

  final bool isSaved;

  /// Разрешённые кнопки кастомной клавиатуры (строки цифр).
  final List<String> enabledKeys;

  /// Выбранные теги (храним текстовые label).
  final List<String> tags;

  /// Раскрыт ли блок тегов на экране.
  final bool isTagsExpanded;

  AddRecordState({
    this.systolic = '',
    this.diastolic = '',
    this.pulse = '',
    this.note = '',
    DateTime? selectedDateTime,
    this.activeField = InputField.systolic,
    this.isSaved = false,
    this.enabledKeys = const [],
    this.tags = const [],
    this.isTagsExpanded = false,
  }) : selectedDateTime = selectedDateTime ?? DateTime.now();

  bool get isValid => ValidationUtils.isFormValid(
    systolic: systolic,
    diastolic: diastolic,
    pulse: pulse,
  );

  AddRecordState copyWith({
    String? systolic,
    String? diastolic,
    String? pulse,
    String? note,
    DateTime? selectedDateTime,
    InputField? activeField,
    bool? isSaved,
    List<String>? enabledKeys,
    List<String>? tags,
    bool? isTagsExpanded,
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
      tags: tags ?? this.tags,
      isTagsExpanded: isTagsExpanded ?? this.isTagsExpanded,
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
    tags,
    isTagsExpanded,
  ];
}
