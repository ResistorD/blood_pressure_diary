import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/repositories/pressure_repository.dart';
import '../../../../core/utils/validation_utils.dart';
import '../../../../core/utils/smart_input_engine.dart';
import '../../../home/data/blood_pressure_model.dart';
import 'add_record_event.dart';
import 'add_record_state.dart';
import 'package:blood_pressure_diary/core/utils/input_field.dart';

class AddRecordBloc extends Bloc<AddRecordEvent, AddRecordState> {
  final PressureRepository _repository;
  int? _editingId;

  AddRecordBloc(this._repository) : super(AddRecordState()) {
    on<EditStarted>(_onEditStarted);
    on<NumberPressed>(_onNumberPressed);
    on<BackspacePressed>(_onBackspacePressed);
    on<FieldChanged>(_onFieldChanged);
    on<NoteChanged>((event, emit) => emit(state.copyWith(note: event.note)));
    on<SaveSubmitted>(_onSaveSubmitted);
    on<DeleteSubmitted>(_onDeleteSubmitted);
    on<DateTimeSet>((event, emit) => emit(state.copyWith(selectedDateTime: event.value)));

    // КРИТИЧНО: Инициализируем кнопки для пустого состояния систолы сразу
    add(const FieldChanged(InputField.systolic));
  }

  void _onNumberPressed(NumberPressed event, Emitter<AddRecordState> emit) {
    if (state.activeField == InputField.none) {
      final ns = state.copyWith(activeField: InputField.systolic);
      emit(ns);
      _updateEnabledKeys(emit, ns);
      return;
    }

    if (!state.enabledKeys.contains(event.number)) return;

    final cur = _getVal(state.activeField);
    final next = cur + event.number;

    // 1) обновляем значение поля
    final ns = _updateStateValue(state, state.activeField, next);

    // 2) авто-переход
    final nextField = _getAutoNextField(ns);

    if (nextField != ns.activeField) {
      final finalState = ns.copyWith(activeField: nextField);
      emit(finalState);
      _updateEnabledKeys(emit, finalState);
    } else {
      emit(ns);
      _updateEnabledKeys(emit, ns);
    }
  }

  InputField _getAutoNextField(AddRecordState s) {
    final val = _getValFrom(s, s.activeField);
    if (val.isEmpty) return s.activeField;

    final sys = int.tryParse(s.systolic);

    if (SmartInputEngine.shouldAutoAdvance(
      field: s.activeField,
      currentText: val,
      systolicValue: sys,
    )) {
      return switch (s.activeField) {
        InputField.systolic => InputField.diastolic,
        InputField.diastolic => InputField.pulse,
        InputField.pulse => InputField.none,
        _ => s.activeField,
      };
    }

    return s.activeField;
  }

  void _updateEnabledKeys(Emitter<AddRecordState> emit, AddRecordState s) {
    final val = _getValFrom(s, s.activeField);
    final sys = int.tryParse(s.systolic);

    const digits = ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9'];
    final allowed = <String>[];

    for (final d in digits) {
      if (SmartInputEngine.isDigitAllowed(
        field: s.activeField,
        currentText: val,
        digit: d,
        systolicValue: sys,
      )) {
        allowed.add(d);
      }
    }

    emit(s.copyWith(enabledKeys: allowed));
  }

  void _onFieldChanged(FieldChanged event, Emitter<AddRecordState> emit) {
    final ns = state.copyWith(activeField: event.field);
    emit(ns);
    _updateEnabledKeys(emit, ns);
  }

  String _getValFrom(AddRecordState s, InputField field) {
    if (field == InputField.systolic) return s.systolic;
    if (field == InputField.diastolic) return s.diastolic;
    if (field == InputField.pulse) return s.pulse;
    return '';
  }

  String _getVal(InputField field) => _getValFrom(state, field);

  void _onEditStarted(EditStarted event, Emitter<AddRecordState> emit) {
    _editingId = event.record.id;
    final ns = state.copyWith(
      systolic: event.record.systolic.toString(),
      diastolic: event.record.diastolic.toString(),
      pulse: event.record.pulse.toString(),
      note: event.record.note,
      selectedDateTime: event.record.dateTime,
      activeField: InputField.systolic,
    );
    emit(ns);
    _updateEnabledKeys(emit, ns);
  }

  AddRecordState _updateStateValue(AddRecordState s, InputField field, String val) {
    if (field == InputField.systolic) return s.copyWith(systolic: val);
    if (field == InputField.diastolic) return s.copyWith(diastolic: val);
    if (field == InputField.pulse) return s.copyWith(pulse: val);
    return s;
  }

  void _onBackspacePressed(BackspacePressed event, Emitter<AddRecordState> emit) {
    final cur = _getVal(state.activeField);
    if (cur.isEmpty) return;

    final next = cur.substring(0, cur.length - 1);
    final ns = _updateStateValue(state, state.activeField, next);
    emit(ns);
    _updateEnabledKeys(emit, ns);
  }

  Future<void> _onSaveSubmitted(SaveSubmitted event, Emitter<AddRecordState> emit) async {
    if (!ValidationUtils.isFormValid(
      systolic: state.systolic,
      diastolic: state.diastolic,
      pulse: state.pulse,
    )) {
      return;
    }

    final record = BloodPressureRecord()
      ..systolic = int.parse(state.systolic)
      ..diastolic = int.parse(state.diastolic)
      ..pulse = int.parse(state.pulse)
      ..note = state.note
      ..dateTime = state.selectedDateTime;

    if (_editingId != null) {
      record.id = _editingId!;
    }

    await _repository.addRecord(record);
    emit(state.copyWith(isSaved: true));
  }

  Future<void> _onDeleteSubmitted(DeleteSubmitted event, Emitter<AddRecordState> emit) async {
    if (_editingId != null) {
      await _repository.deleteRecord(_editingId!);
      emit(state.copyWith(isSaved: true));
    }
  }
}
