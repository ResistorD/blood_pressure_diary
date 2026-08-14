import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/repositories/pressure_repository.dart';
import '../../data/blood_pressure_model.dart';
import 'home_event.dart';
import 'home_state.dart';

class HomeBloc extends Bloc<HomeEvent, HomeState> {
  final Stream<List<BloodPressureRecord>> Function() _watchRecords;
  final Future<void> Function(int id) _deleteRecord;
  final Future<void> Function(BloodPressureRecord record) _restoreRecord;
  StreamSubscription<List<BloodPressureRecord>>? _recordsSub;

  HomeBloc(PressureRepository repository)
    : _watchRecords = repository.getAllRecordsStream,
      _deleteRecord = repository.deleteRecord,
      _restoreRecord = repository.addRecord,
      super(HomeLoading()) {
    _registerHandlers();
    add(LoadHomeData());
  }

  @visibleForTesting
  HomeBloc.test({
    required Stream<List<BloodPressureRecord>> Function() watchRecords,
    required Future<void> Function(int id) deleteRecord,
    required Future<void> Function(BloodPressureRecord record) restoreRecord,
  }) : _watchRecords = watchRecords,
       _deleteRecord = deleteRecord,
       _restoreRecord = restoreRecord,
       super(HomeLoading()) {
    _registerHandlers();
  }

  void _registerHandlers() {
    on<LoadHomeData>(_onLoadData);
    on<HomeRecordsUpdated>(_onRecordsUpdated);
    on<HomeRecordsLoadFailed>(_onRecordsLoadFailed);
    on<HomeDeleteRecordRequested>(_onDeleteRecordRequested);
    on<HomeRestoreRecordRequested>(_onRestoreRecordRequested);
  }

  Future<void> _onLoadData(LoadHomeData event, Emitter<HomeState> emit) async {
    await _recordsSub?.cancel();
    _recordsSub = _watchRecords().listen(
      (records) => add(HomeRecordsUpdated(records)),
      onError: (Object error) => add(HomeRecordsLoadFailed(error)),
    );
  }

  void _onRecordsUpdated(HomeRecordsUpdated event, Emitter<HomeState> emit) {
    emit(HomeLoaded(event.records));
  }

  void _onRecordsLoadFailed(
    HomeRecordsLoadFailed event,
    Emitter<HomeState> emit,
  ) {
    emit(HomeError(event.error.toString()));
  }

  Future<void> _onDeleteRecordRequested(
    HomeDeleteRecordRequested event,
    Emitter<HomeState> emit,
  ) async {
    try {
      await _deleteRecord(event.recordId);
      event.completer.complete();
    } catch (error, stackTrace) {
      event.completer.completeError(error, stackTrace);
    }
  }

  Future<void> _onRestoreRecordRequested(
    HomeRestoreRecordRequested event,
    Emitter<HomeState> emit,
  ) async {
    try {
      await _restoreRecord(event.record);
      event.completer.complete();
    } catch (error, stackTrace) {
      event.completer.completeError(error, stackTrace);
    }
  }

  @override
  Future<void> close() async {
    await _recordsSub?.cancel();
    return super.close();
  }
}
