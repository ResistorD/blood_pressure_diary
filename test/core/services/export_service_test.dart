import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/core/services/export_service.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('PDF profile mapping receives patient name', () {
    final service = ExportService();
    final profile = UserProfile(name: 'Ivan Petrov', age: 44);

    final fields = service.pdfProfileFieldsForTest(
      profile,
      DateTime(2026, 6, 18),
    );

    expect(fields.patientName, 'Ivan Petrov');
  });

  test('PDF profile mapping receives calculated age', () {
    final service = ExportService();
    final profile = UserProfile(name: 'Ivan Petrov', age: 19800620);

    final fields = service.pdfProfileFieldsForTest(
      profile,
      DateTime(2026, 6, 18),
    );

    expect(fields.age, '45');
  });
}
