import 'package:flutter_bloc/flutter_bloc.dart';
import '../../../../core/repositories/pressure_repository.dart';
import '../../data/blood_pressure_model.dart';
import 'home_event.dart';
import 'home_state.dart';

class HomeBloc extends Bloc<HomeEvent, HomeState> {
  final PressureRepository _repository;

  HomeBloc(this._repository) : super(HomeLoading()) {
    on<LoadHomeData>(_onLoadData);
    add(LoadHomeData());
  }

  Future<void> _onLoadData(LoadHomeData event, Emitter<HomeState> emit) async {
    // Явно типизируем стрим, чтобы избежать ошибки Object?
    await emit.forEach<List<BloodPressureRecord>>(
      _repository.getAllRecordsStream(),
      onData: (records) => HomeLoaded(records),
      onError: (error, stackTrace) => HomeError(error.toString()),
    );
  }
}