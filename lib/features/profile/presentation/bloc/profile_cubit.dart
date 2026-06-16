import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_state.dart';

class ProfileCubit extends Cubit<ProfileState> {
  final Future<UserProfile> Function() _getOrCreateProfile;
  final Stream<UserProfile> Function() _watchProfile;
  final Future<void> Function(UserProfile profile) _saveProfile;

  StreamSubscription<UserProfile>? _profileSub;

  ProfileCubit(IsarService isarService)
    : _getOrCreateProfile = isarService.getOrCreateProfile,
      _watchProfile = isarService.watchProfile,
      _saveProfile = isarService.saveProfile,
      super(ProfileInitial()) {
    _bind();
  }

  @visibleForTesting
  ProfileCubit.test({
    required Future<UserProfile> Function() getOrCreateProfile,
    required Stream<UserProfile> Function() watchProfile,
    Future<void> Function(UserProfile profile)? saveProfile,
    bool autoBind = true,
  }) : _getOrCreateProfile = getOrCreateProfile,
       _watchProfile = watchProfile,
       _saveProfile = saveProfile ?? ((_) async {}),
       super(ProfileInitial()) {
    if (autoBind) {
      _bind();
    }
  }

  Future<void> _bind() async {
    await _getOrCreateProfile();
    if (isClosed) return;

    await _profileSub?.cancel();
    _profileSub = _watchProfile().listen((profile) {
      if (isClosed) return;
      emit(ProfileLoaded(profile));
    });
  }

  @override
  Future<void> close() async {
    await _profileSub?.cancel();
    return super.close();
  }

  Future<void> loadProfile({bool force = false}) async {
    if (!force && state is ProfileLoaded) return;
    emit(ProfileLoading());
    try {
      final profile = await _getOrCreateProfile();
      if (isClosed) return;
      emit(ProfileLoaded(profile));
    } catch (e) {
      if (isClosed) return;
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
    final current = await _getOrCreateProfile();

    final updated = UserProfile()
      ..id = 0
      ..name = name ?? current.name
      ..age = age ?? current.age
      ..gender = gender ?? current.gender
      ..weight = weight ?? current.weight
      ..targetSystolic = targetSystolic ?? current.targetSystolic
      ..targetDiastolic = targetDiastolic ?? current.targetDiastolic
      ..accountLinked = current.accountLinked
      ..accountEmail = current.accountEmail
      ..accountProvider = current.accountProvider;

    await _saveProfile(updated);
  }

  Future<void> linkAccount({
    required String provider,
    required String email,
  }) async {
    final current = await _getOrCreateProfile();

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

    await _saveProfile(updated);
  }

  Future<void> unlinkAccount() async {
    final current = await _getOrCreateProfile();

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

    await _saveProfile(updated);
  }
}
