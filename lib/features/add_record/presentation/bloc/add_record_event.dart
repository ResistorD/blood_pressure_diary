import 'package:equatable/equatable.dart';
// Импортируем модель, чтобы событие EditStarted знало о BloodPressureRecord
import '../../../home/data/blood_pressure_model.dart';
import 'package:blood_pressure_diary/core/utils/input_field.dart';


abstract class AddRecordEvent extends Equatable {
  const AddRecordEvent();
  @override
  List<Object?> get props => [];
}

// СОБЫТИЕ ДЛЯ РЕДАКТИРОВАНИЯ
class EditStarted extends AddRecordEvent {
  final BloodPressureRecord record;
  const EditStarted(this.record);

  @override
  List<Object?> get props => [record];
}

class NumberPressed extends AddRecordEvent {
  final String number;
  const NumberPressed(this.number);
  @override
  List<Object?> get props => [number];
}

class BackspacePressed extends AddRecordEvent {}

class FieldChanged extends AddRecordEvent {
  final InputField field;
  const FieldChanged(this.field);
  @override
  List<Object?> get props => [field];
}

// СОБЫТИЕ ДЛЯ ЗАМЕТОК
class NoteChanged extends AddRecordEvent {
  final String note;
  const NoteChanged(this.note);

  @override
  List<Object?> get props => [note];
}

class TagToggled extends AddRecordEvent {
  final String tag;

  const TagToggled(this.tag);
}

class TagsExpandedToggled extends AddRecordEvent {
  const TagsExpandedToggled();
}

class EmotionChanged extends AddRecordEvent {
  final String emotion;
  const EmotionChanged(this.emotion);
  @override
  List<Object?> get props => [emotion];
}

class EmojiAppended extends AddRecordEvent {
  final String emoji;
  const EmojiAppended(this.emoji);

  @override
  List<Object?> get props => [emoji];
}

class SaveSubmitted extends AddRecordEvent {}
class DeleteSubmitted extends AddRecordEvent {}

class DateTimeSet extends AddRecordEvent {
  final DateTime value;
  const DateTimeSet(this.value);
  @override
  List<Object?> get props => [value];
}

class DraftLoaded extends AddRecordEvent {
  final String systolic;
  final String diastolic;
  final String pulse;
  final String note;
  final DateTime selectedDateTime;
  final List<String> tags;

  const DraftLoaded({
    required this.systolic,
    required this.diastolic,
    required this.pulse,
    required this.note,
    required this.selectedDateTime,
    required this.tags,
  });

  @override
  List<Object?> get props => [
    systolic,
    diastolic,
    pulse,
    note,
    selectedDateTime,
    tags,
  ];
}
