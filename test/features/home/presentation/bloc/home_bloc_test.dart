import 'dart:async';

import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';
import 'package:blood_pressure_diary/features/home/presentation/bloc/home_bloc.dart';
import 'package:blood_pressure_diary/features/home/presentation/bloc/home_event.dart';
import 'package:blood_pressure_diary/features/home/presentation/bloc/home_state.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  BloodPressureRecord record() => BloodPressureRecord()
    ..id = 1
    ..dateTime = DateTime(2026, 1, 1, 8)
    ..systolic = 120
    ..diastolic = 80
    ..pulse = 70;

  HomeBloc buildBloc({
    Future<void> Function(int id)? deleteRecord,
    Future<void> Function(BloodPressureRecord record)? restoreRecord,
  }) {
    return HomeBloc.test(
      watchRecords: () => const Stream<List<BloodPressureRecord>>.empty(),
      deleteRecord: deleteRecord ?? (_) async {},
      restoreRecord: restoreRecord ?? (_) async {},
    );
  }

  test('delete success completes event completer', () async {
    final bloc = buildBloc();
    final completer = Completer<void>();

    bloc.add(HomeDeleteRecordRequested(recordId: 1, completer: completer));

    await expectLater(completer.future, completes);
    await bloc.close();
  });

  test('delete failure completes event completer with error', () async {
    final bloc = buildBloc(deleteRecord: (_) async => throw StateError('fail'));
    final completer = Completer<void>();

    bloc.add(HomeDeleteRecordRequested(recordId: 1, completer: completer));

    await expectLater(completer.future, throwsA(isA<StateError>()));
    await bloc.close();
  });

  test('restore success completes event completer', () async {
    final bloc = buildBloc();
    final completer = Completer<void>();

    bloc.add(
      HomeRestoreRecordRequested(record: record(), completer: completer),
    );

    await expectLater(completer.future, completes);
    await bloc.close();
  });

  test('restore failure completes event completer with error', () async {
    final bloc = buildBloc(
      restoreRecord: (_) async => throw StateError('restore fail'),
    );
    final completer = Completer<void>();

    bloc.add(
      HomeRestoreRecordRequested(record: record(), completer: completer),
    );

    await expectLater(completer.future, throwsA(isA<StateError>()));
    await bloc.close();
  });

  test(
    'repeated LoadHomeData does not keep duplicate active subscriptions',
    () async {
      var listenCount = 0;
      var cancelCount = 0;
      late StreamController<List<BloodPressureRecord>> controller;

      controller = StreamController<List<BloodPressureRecord>>.broadcast(
        onListen: () => listenCount++,
        onCancel: () => cancelCount++,
      );

      final bloc = HomeBloc.test(
        watchRecords: () => controller.stream,
        deleteRecord: (_) async {},
        restoreRecord: (_) async {},
      );

      bloc.add(LoadHomeData());
      await Future<void>.delayed(Duration.zero);
      bloc.add(LoadHomeData());
      await Future<void>.delayed(Duration.zero);

      final states = <HomeState>[];
      final stateSub = bloc.stream.listen(states.add);
      final item = record()..id = 2;

      controller.add([item]);
      await Future<void>.delayed(Duration.zero);

      expect(listenCount, 2);
      expect(cancelCount, 1);
      expect(states.whereType<HomeLoaded>().length, 1);
      expect((states.single as HomeLoaded).records, [item]);

      await stateSub.cancel();
      await bloc.close();
      await controller.close();
    },
  );
}
