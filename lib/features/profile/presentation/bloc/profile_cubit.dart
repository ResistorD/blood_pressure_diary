import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';

import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_state.dart';

class ProfileCubit extends Cubit<ProfileState> {
  final IsarService _isarService;
  StreamSubscription<UserProfile>? _profileSub;

  ProfileCubit(this._isarService) : super(ProfileInitial()) {
    _bind();
  }

  Future<void> _bind() async {
    // Гарантируем наличие singleton-профиля.
    await _isarService.getOrCreateProfile();

    await _profileSub?.cancel();
    _profileSub = _isarService.watchProfile().listen((profile) {
      emit(ProfileLoaded(profile));
    });
  }

  @override
  Future<void> close() async {
    await _profileSub?.cancel();
    return super.close();
  }

  Future<void> loadProfile() async {
    // Оставляю метод для совместимости с текущим кодом навигации.
    // Реальная загрузка идёт через подписку на Isar.
    if (state is ProfileLoaded) return;
    emit(ProfileLoading());
    try {
      final profile = await _isarService.getOrCreateProfile();
      emit(ProfileLoaded(profile));
    } catch (e) {
      emit(ProfileError(e.toString()));
    }
  }

  Future<void> updateProfile({
    String? name,
    int? age,
    String? gender,
    double? weight,
    int? targetSystolic,
    int? targetDiastolic,
  }) async {
    // Можно обновлять даже если ещё не успели получить Loaded.
    final current = await _isarService.getOrCreateProfile();

    final updated = UserProfile()
      ..id = 0
      ..name = name ?? current.name
      ..age = age ?? current.age
      ..gender = gender ?? current.gender
      ..weight = weight ?? current.weight
      ..targetSystolic = targetSystolic ?? current.targetSystolic
      ..targetDiastolic = targetDiastolic ?? current.targetDiastolic
      // сохраняем аккаунт, чтобы updateProfile не “стирал” его
      ..accountLinked = current.accountLinked
      ..accountEmail = current.accountEmail
      ..accountProvider = current.accountProvider;

    await _isarService.saveProfile(updated);
  }

  // --- Account link (локально: храним в Isar) ---
  Future<void> linkAccount({
    required String provider,
    required String email,
  }) async {
    final current = await _isarService.getOrCreateProfile();

    final updated = UserProfile()
      ..id = 0
      ..name = current.name
      ..age = current.age
      ..gender = current.gender
      ..weight = current.weight
      ..targetSystolic = current.targetSystolic
      ..targetDiastolic = current.targetDiastolic
      ..accountLinked = true
      ..accountProvider = provider.trim()
      ..accountEmail = email.trim();

    await _isarService.saveProfile(updated);
  }

  Future<void> unlinkAccount() async {
    final current = await _isarService.getOrCreateProfile();

    final updated = UserProfile()
      ..id = 0
      ..name = current.name
      ..age = current.age
      ..gender = current.gender
      ..weight = current.weight
      ..targetSystolic = current.targetSystolic
      ..targetDiastolic = current.targetDiastolic
      ..accountLinked = false
      ..accountProvider = ''
      ..accountEmail = '';

    await _isarService.saveProfile(updated);
  }
}
