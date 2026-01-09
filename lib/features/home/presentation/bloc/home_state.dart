import 'package:equatable/equatable.dart';
import '../../data/blood_pressure_model.dart';

abstract class HomeState extends Equatable {
  const HomeState();
  @override
  List<Object> get props => [];
}

class HomeLoading extends HomeState {}

class HomeLoaded extends HomeState {
  final List<BloodPressureRecord> records;
  const HomeLoaded(this.records);

  @override
  List<Object> get props => [records];
}

class HomeError extends HomeState {
  final String message;
  const HomeError(this.message);
}