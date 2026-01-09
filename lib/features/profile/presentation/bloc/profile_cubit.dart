import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_state.dart';

class ProfileCubit extends Cubit<ProfileState> {
  final IsarService _isarService;

  ProfileCubit(this._isarService) : super(ProfileInitial());

  Future<void> loadProfile() async {
    if (state is ProfileLoaded) return;
    
    emit(ProfileLoading());
    try {
      final profile = await _isarService.getProfile();
      if (profile != null) {
        emit(ProfileLoaded(profile));
      } else {
        final defaultProfile = UserProfile();
        await _isarService.saveProfile(defaultProfile);
        emit(ProfileLoaded(defaultProfile));
      }
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
    if (state is ProfileLoaded) {
      final currentProfile = (state as ProfileLoaded).profile;
      
      final updatedProfile = UserProfile()
        ..id = 0
        ..name = name ?? currentProfile.name
        ..age = age ?? currentProfile.age
        ..gender = gender ?? currentProfile.gender
        ..weight = weight ?? currentProfile.weight
        ..targetSystolic = targetSystolic ?? currentProfile.targetSystolic
        ..targetDiastolic = targetDiastolic ?? currentProfile.targetDiastolic;

      await _isarService.saveProfile(updatedProfile);
      emit(ProfileLoaded(updatedProfile));
    }
  }
}
