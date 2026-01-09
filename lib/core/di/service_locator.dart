import 'package:get_it/get_it.dart';
import 'package:isar/isar.dart';
import 'package:blood_pressure_diary/features/home/presentation/bloc/home_bloc.dart';
import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/repositories/pressure_repository.dart';
import 'package:blood_pressure_diary/features/add_record/presentation/bloc/add_record_bloc.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_cubit.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_cubit.dart';
import 'package:blood_pressure_diary/core/services/export_service.dart';
import 'package:blood_pressure_diary/core/services/notification_service.dart';

final getIt = GetIt.instance;

Future<void> setupLocator(Isar isar) async {
  getIt.registerSingleton<Isar>(isar);
  getIt.registerSingleton<IsarService>(IsarService(isar));
  getIt.registerSingleton<ExportService>(ExportService());
  
  final notificationService = NotificationService();
  await notificationService.initialize();
  getIt.registerSingleton<NotificationService>(notificationService);

  // 2. Репозиторий (зависит от IsarService)
  getIt.registerLazySingleton<PressureRepository>(
        () => PressureRepository(getIt<IsarService>()),
  );

  // 3. BLoC (зависит от репозитория)
  getIt.registerFactory<HomeBloc>(() => HomeBloc(getIt<PressureRepository>()));
  
  getIt.registerFactory(() => AddRecordBloc(getIt<PressureRepository>()));
  getIt.registerSingleton<ProfileCubit>(ProfileCubit(getIt<IsarService>()));
  
  // SettingsCubit как синглтон, чтобы настройки были доступны везде
  getIt.registerSingleton(SettingsCubit(
    getIt<IsarService>(),
    getIt<PressureRepository>(),
    getIt<ExportService>(),
    getIt<NotificationService>(),
  ));
}
