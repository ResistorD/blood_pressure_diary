import 'dart:async';

import 'package:equatable/equatable.dart';

import '../../data/blood_pressure_model.dart';

abstract class HomeEvent extends Equatable {
  const HomeEvent();
  @override
  List<Object> get props => [];
}

class LoadHomeData extends HomeEvent {}

class HomeRecordsUpdated extends HomeEvent {
  final List<BloodPressureRecord> records;

  const HomeRecordsUpdated(this.records);

  @override
  List<Object> get props => [records];
}

class HomeRecordsLoadFailed extends HomeEvent {
  final Object error;

  const HomeRecordsLoadFailed(this.error);

  @override
  List<Object> get props => [error];
}

class HomeDeleteRecordRequested extends HomeEvent {
  final int recordId;
  final Completer<void> completer;

  const HomeDeleteRecordRequested({
    required this.recordId,
    required this.completer,
  });

  @override
  List<Object> get props => [recordId];
}

class HomeRestoreRecordRequested extends HomeEvent {
  final BloodPressureRecord record;
  final Completer<void> completer;

  const HomeRestoreRecordRequested({
    required this.record,
    required this.completer,
  });

  @override
  List<Object> get props => [record];
}
