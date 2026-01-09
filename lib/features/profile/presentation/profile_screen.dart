import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_cubit.dart';
import 'package:blood_pressure_diary/features/profile/presentation/bloc/profile_state.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const ProfileView();
  }
}

class ProfileView extends StatefulWidget {
  const ProfileView({super.key});

  @override
  State<ProfileView> createState() => _ProfileViewState();
}

class _ProfileViewState extends State<ProfileView> {
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _ageController = TextEditingController();
  final TextEditingController _weightController = TextEditingController();

  @override
  void initState() {
    super.initState();
    final state = context.read<ProfileCubit>().state;
    if (state is ProfileLoaded) {
      _nameController.text = state.profile.name;
      _ageController.text = state.profile.age > 0 ? state.profile.age.toString() : '';
      _weightController.text = state.profile.weight > 0 ? state.profile.weight.toString() : '';
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _ageController.dispose();
    _weightController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;

    return Scaffold(
      backgroundColor: AppUI.background,
      appBar: AppBar(
        title: Text(
          l10n.profile,
          style: const TextStyle(
            color: Colors.black,
            fontFamily: 'Inter',
            fontWeight: FontWeight.bold,
          ),
        ),
        backgroundColor: Colors.white,
        elevation: 0,
      ),
      body: BlocConsumer<ProfileCubit, ProfileState>(
        listenWhen: (prev, curr) => prev is ProfileInitial && curr is ProfileLoaded,
        listener: (context, state) {
          if (state is ProfileLoaded) {
            _nameController.text = state.profile.name;
            _ageController.text = state.profile.age > 0 ? state.profile.age.toString() : '';
            _weightController.text = state.profile.weight > 0 ? state.profile.weight.toString() : '';
          }
        },
        builder: (context, state) {
          if (state is ProfileLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          if (state is ProfileLoaded) {
            final profile = state.profile;
            return SingleChildScrollView(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  const SizedBox(height: 20),
                  const CircleAvatar(
                    radius: 50,
                    backgroundColor: AppUI.headerBlue,
                    child: Icon(Icons.person, size: 60, color: Colors.white),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: _nameController,
                    textAlign: TextAlign.center,
                    decoration: InputDecoration(
                      hintText: l10n.name,
                      border: InputBorder.none,
                      hintStyle: const TextStyle(fontFamily: 'Inter'),
                    ),
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      fontFamily: 'Inter',
                    ),
                    onChanged: (value) => context.read<ProfileCubit>().updateProfile(name: value),
                  ),
                  const SizedBox(height: 32),
                  _buildProfileFields(context, profile, l10n),
                  const SizedBox(height: 32),
                  _buildGoalSection(context, profile, l10n),
                  const SizedBox(height: 32),
                  _buildPremiumCard(l10n),
                  const SizedBox(height: 40),
                ],
              ),
            );
          }

          return const SizedBox.shrink();
        },
      ),
    );
  }

  Widget _buildProfileFields(BuildContext context, dynamic profile, AppLocalizations l10n) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 10,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        children: [
          _buildFieldRow(
            l10n.age,
            TextField(
              controller: _ageController,
              keyboardType: TextInputType.number,
              textAlign: TextAlign.end,
              decoration: const InputDecoration(border: InputBorder.none),
              onChanged: (value) {
                final age = int.tryParse(value) ?? 0;
                context.read<ProfileCubit>().updateProfile(age: age);
              },
            ),
          ),
          const Divider(),
          _buildFieldRow(
            l10n.weight,
            TextField(
              controller: _weightController,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              textAlign: TextAlign.end,
              decoration: const InputDecoration(border: InputBorder.none),
              onChanged: (value) {
                final weight = double.tryParse(value) ?? 0.0;
                context.read<ProfileCubit>().updateProfile(weight: weight);
              },
            ),
          ),
          const Divider(),
          _buildFieldRow(
            l10n.gender,
            DropdownButton<String>(
              value: profile.gender,
              underline: const SizedBox(),
              items: [
                DropdownMenuItem(value: 'male', child: Text(l10n.male)),
                DropdownMenuItem(value: 'female', child: Text(l10n.female)),
                DropdownMenuItem(value: 'other', child: Text(l10n.other)),
              ],
              onChanged: (value) {
                if (value != null) {
                  context.read<ProfileCubit>().updateProfile(gender: value);
                }
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFieldRow(String label, Widget trailing) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(
            label,
            style: const TextStyle(
              fontFamily: 'Inter',
              fontSize: 16,
              color: Colors.grey,
            ),
          ),
          SizedBox(width: 100, child: trailing),
        ],
      ),
    );
  }

  Widget _buildGoalSection(BuildContext context, dynamic profile, AppLocalizations l10n) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 12),
          child: Text(
            l10n.myGoal,
            style: const TextStyle(
              fontFamily: 'Inter',
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: AppUI.headerBlue,
            ),
          ),
        ),
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Column(
            children: [
              _buildTargetInput(
                context,
                l10n.systolic,
                profile.targetSystolic,
                (val) => context.read<ProfileCubit>().updateProfile(targetSystolic: val),
              ),
              const Divider(),
              _buildTargetInput(
                context,
                l10n.diastolic,
                profile.targetDiastolic,
                (val) => context.read<ProfileCubit>().updateProfile(targetDiastolic: val),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildTargetInput(BuildContext context, String label, int value, Function(int) onChanged) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label, style: const TextStyle(fontFamily: 'Inter')),
        Row(
          children: [
            IconButton(
              icon: const Icon(Icons.remove_circle_outline),
              onPressed: () => onChanged(value - 1),
            ),
            Text(
              '$value',
              style: const TextStyle(
                fontFamily: 'Inter',
                fontSize: 18,
                fontWeight: FontWeight.bold,
              ),
            ),
            IconButton(
              icon: const Icon(Icons.add_circle_outline),
              onPressed: () => onChanged(value + 1),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildPremiumCard(AppLocalizations l10n) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [AppUI.headerBlue, Color(0xFF64B5F6)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: AppUI.headerBlue.withOpacity(0.3),
            blurRadius: 15,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.star, color: Colors.amber, size: 30),
              const SizedBox(width: 8),
              Text(
                l10n.premium,
                style: const TextStyle(
                  fontFamily: 'Inter',
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            l10n.oneTimePayment,
            style: const TextStyle(
              fontFamily: 'Inter',
              color: Colors.white,
              fontSize: 16,
            ),
          ),
          const SizedBox(height: 20),
          ElevatedButton(
            onPressed: () {},
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white,
              foregroundColor: AppUI.headerBlue,
              minimumSize: const Size(double.infinity, 50),
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              elevation: 0,
            ),
            child: Text(
              l10n.buyPremium,
              style: const TextStyle(
                fontFamily: 'Inter',
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
