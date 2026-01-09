import 'input_field.dart';
import 'pressure_field.dart';

PressureField? toPressureField(InputField f) {
  return switch (f) {
    InputField.systolic => PressureField.systolic,
    InputField.diastolic => PressureField.diastolic,
    InputField.pulse => PressureField.pulse,
    _ => null,
  };
}
