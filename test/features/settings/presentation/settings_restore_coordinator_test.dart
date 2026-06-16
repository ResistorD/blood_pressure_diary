import 'package:blood_pressure_diary/features/settings/presentation/settings_restore_coordinator.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'successful restore refreshes settings and profile with force',
    () async {
      final calls = <String>[];
      bool? profileForce;

      await const SettingsRestoreCoordinator().restoreAndRefresh(
        restoreBackup: () async => calls.add('restore'),
        reloadSettings: () async => calls.add('settings'),
        loadProfile: ({required force}) async {
          profileForce = force;
          calls.add('profile');
        },
      );

      expect(calls, ['restore', 'settings', 'profile']);
      expect(profileForce, isTrue);
    },
  );
}
