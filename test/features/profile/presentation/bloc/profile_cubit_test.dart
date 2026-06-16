import 'dart:async';

import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_cubit.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_state.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  UserProfile profile(String name) => UserProfile(name: name)..id = 0;

  test('close cancels profile subscription', () async {
    var canceled = false;
    final controller = StreamController<UserProfile>(
      onCancel: () {
        canceled = true;
      },
    );

    final cubit = ProfileCubit.test(
      getOrCreateProfile: () async => profile('initial'),
      watchProfile: () => controller.stream,
    );

    await Future<void>.delayed(Duration.zero);
    await cubit.close();

    expect(canceled, isTrue);
    await controller.close();
  });

  test(
    'loadProfile(force: true) reloads profile when already loaded',
    () async {
      final profiles = [profile('first'), profile('second')];
      var reads = 0;

      final cubit = ProfileCubit.test(
        getOrCreateProfile: () async => profiles[reads++],
        watchProfile: () => const Stream<UserProfile>.empty(),
        autoBind: false,
      );

      await cubit.loadProfile();
      expect((cubit.state as ProfileLoaded).profile.name, 'first');
      expect(reads, 1);

      await cubit.loadProfile();
      expect((cubit.state as ProfileLoaded).profile.name, 'first');
      expect(reads, 1);

      await cubit.loadProfile(force: true);
      expect((cubit.state as ProfileLoaded).profile.name, 'second');
      expect(reads, 2);

      await cubit.close();
    },
  );
}
