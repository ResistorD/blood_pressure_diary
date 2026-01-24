import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_state.dart';

class ProfileCubit extends Cubit<ProfileState> {
  final IsarService _isarService;
  StreamSubscription<UserProfile>? _profileSub;
  bool _isSubscribed = false;

  ProfileCubit(this._isarService) : super(ProfileInitial());

  Future<void> loadProfile() async {
    if (_isSubscribed) return;

    emit(ProfileLoading());
    try {
      final profile = await _isarService.getOrCreateProfile();
      emit(ProfileLoaded(profile));
      _profileSub?.cancel();
      _profileSub = _isarService.watchProfile().listen(
        (profile) {
          emit(ProfileLoaded(profile));
        },
        onError: (error) {
          emit(ProfileError(error.toString()));
        },
      );
      _isSubscribed = true;
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
    if (state is! ProfileLoaded) return;

    final current = (state as ProfileLoaded).profile;

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
    emit(ProfileLoaded(updated));
  }

  // --- Account link (реально: сохраняем в Isar) ---
  Future<void> linkAccount({
    required String provider,
    required String email,
  }) async {
    if (state is! ProfileLoaded) return;

    final current = (state as ProfileLoaded).profile;

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
    emit(ProfileLoaded(updated));
  }

  Future<void> unlinkAccount() async {
    if (state is! ProfileLoaded) return;

    final current = (state as ProfileLoaded).profile;

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
    emit(ProfileLoaded(updated));
  }

  @override
  Future<void> close() async {
    await _profileSub?.cancel();
    return super.close();
  }
}
