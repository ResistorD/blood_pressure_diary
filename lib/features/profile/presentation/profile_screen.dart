import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/database/models/user_profile.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/theme/scale.dart';
import '../../../l10n/generated/app_localizations.dart';

import 'bloc/profile_cubit.dart';
import 'bloc/profile_state.dart';
import 'widgets/profile_form_widgets.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});
  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    final isDark = Theme.of(context).brightness == Brightness.dark;

    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final shadows = context.appShadow;
    final text = context.appText;

    final headerH = dp(context, space.s128);
    final side = context.horizontalPadding;

    final cardR = dp(context, radii.r10);

    final fieldH = dp(context, space.s48);
    final fieldR = dp(context, radii.r10);

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final headerTopInset = MediaQuery.paddingOf(context).top;

    // UI-only: в макете показан пример даты
    const demoDob = '25.12.1980';

    String? formatDob(int stored) {
      // Храним дату рождения как YYYYMMDD в поле age (чтобы не трогать Isar-схему).
      // Если stored выглядит как "обычный возраст" (0..150) — даты нет.
      if (stored < 19000101) return null;
      final s = stored.toString().padLeft(8, '0');
      final yyyy = s.substring(0, 4);
      final mm = s.substring(4, 6);
      final dd = s.substring(6, 8);
      return '$dd.$mm.$yyyy';
    }

    // Плотнее по Y — главный фикс
    final pad12 = dp(context, space.s12);
    final pad10 = dp(context, space.s10);
    final pad8 = dp(context, space.s8);
    final pad6 = dp(context, space.s6);
    final pad4 = dp(context, space.s4);
    final pad2 = dp(context, space.s2);

    final titleStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs24),
      fontWeight: text.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final sectionTitleStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs16),
      fontWeight: text.w600,
      color: colors.textPrimary,
      height: 1.0,
    );

    final hintStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs12),
      fontWeight: text.w400,
      color: colors.textPrimary,
      height: 1.0,
    );

    final labelStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs14),
      fontWeight: text.w400,
      color: colors.textPrimary,
      height: 1.0,
    );

    final valueStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs20),
      fontWeight: text.w500,
      color: colors.textPrimary,
      height: 1.0,
    );

    Widget wideField({required String textValue, VoidCallback? onTap}) {
      final bg = isDark ? colors.surfaceAlt : colors.background;
      return ProfileWideField(
        textValue: textValue,
        onTap: onTap,
        height: fieldH,
        borderRadius: fieldR,
        backgroundColor: bg,
        valueStyle: valueStyle,
        space: space,
      );
    }

    Widget valueBox({required String textValue, VoidCallback? onTap}) {
      final w = dp(context, space.s120 + space.s16 + space.s1); // 137
      final bg = isDark ? colors.surfaceAlt : colors.background;

      return ProfileValueBox(
        textValue: textValue,
        onTap: onTap,
        width: w,
        height: fieldH,
        borderRadius: fieldR,
        backgroundColor: bg,
        valueStyle: valueStyle,
        space: space,
      );
    }

    Widget segPill({
      required String title,
      required bool selected,
      required VoidCallback onTap,
      required Color activeBg,
      required Color inactiveText,
      required Color activeText,
    }) {
      return ProfileSegmentPill(
        title: title,
        selected: selected,
        onTap: onTap,
        height: fieldH,
        borderRadius: fieldR,
        activeBackground: activeBg,
        inactiveText: inactiveText,
        activeText: activeText,
        valueStyle: valueStyle,
      );
    }

    Widget normsBlock({
      required String topValue,
      required String bottomValue,
      VoidCallback? onTapTop,
      VoidCallback? onTapBottom,
    }) {
      final fieldBg = isDark ? colors.surfaceAlt : colors.background;
      final borderColor = fieldBg;
      final borderW = dp(context, space.s1);

      final labelLeftPad = dp(context, space.s12);
      final betweenRows = pad4;

      return Container(
        width: double.infinity,
        decoration: BoxDecoration(
          border: Border.all(color: borderColor, width: borderW),
          borderRadius: BorderRadius.circular(fieldR),
        ),
        padding: EdgeInsets.all(pad2),
        child: Column(
          children: [
            SizedBox(
              height: fieldH,
              child: Row(
                children: [
                  Expanded(
                    child: Padding(
                      padding: EdgeInsets.only(left: labelLeftPad),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: Text(l10n.systolic, style: valueStyle),
                      ),
                    ),
                  ),
                  valueBox(textValue: topValue, onTap: onTapTop),
                ],
              ),
            ),
            SizedBox(height: betweenRows),
            SizedBox(
              height: fieldH,
              child: Row(
                children: [
                  Expanded(
                    child: Padding(
                      padding: EdgeInsets.only(left: labelLeftPad),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: Text(l10n.diastolic, style: valueStyle),
                      ),
                    ),
                  ),
                  valueBox(textValue: bottomValue, onTap: onTapBottom),
                ],
              ),
            ),
          ],
        ),
      );
    }

    DateTime? tryParseDob(int stored) {
      if (stored < 19000101) return null;
      final s = stored.toString().padLeft(8, '0');
      final yyyy = int.tryParse(s.substring(0, 4));
      final mm = int.tryParse(s.substring(4, 6));
      final dd = int.tryParse(s.substring(6, 8));
      if (yyyy == null || mm == null || dd == null) return null;
      return DateTime(yyyy, mm, dd);
    }

    Future<void> pickDob(BuildContext context, UserProfile profile) async {
      final now = DateTime.now();
      final initial = tryParseDob(profile.age) ?? DateTime(now.year - 30, 1, 1);
      final cubit = context.read<ProfileCubit>();

      final picked = await showDatePicker(
        context: context,
        initialDate: initial,
        firstDate: DateTime(1900, 1, 1),
        lastDate: DateTime(now.year, 12, 31),
      );

      if (picked == null) return;

      final stored = (picked.year * 10000) + (picked.month * 100) + picked.day;
      cubit.updateProfile(age: stored);
    }

    void showNameInputSheet(BuildContext context, UserProfile profile) {
      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (_) => ProfileTextInputSheet(
          title: l10n.name,
          buttonTitle: l10n.save,
          initialValue: profile.name.isEmpty ? '' : profile.name,
          keyboardType: TextInputType.text,
          onSubmit: (value) {
            context.read<ProfileCubit>().updateProfile(name: value);
          },
          sheetBackground: colors.surface,
          fieldBackground: isDark ? colors.surfaceAlt : colors.background,
          buttonBackground: isDark ? AppPalette.dark900 : AppPalette.blue900,
          buttonForeground: isDark ? colors.textPrimary : colors.textOnBrand,
          sheetRadius: dp(context, radii.r10),
          fieldHeight: fieldH,
          fieldRadius: fieldR,
          titleStyle: labelStyle,
          valueStyle: valueStyle,
          buttonStyle: valueStyle.copyWith(
            fontWeight: text.w600,
            color: isDark ? colors.textPrimary : colors.textOnBrand,
          ),
          shadow: shadows.card,
          space: space,
        ),
      );
    }

    void showIntInputSheet(
      BuildContext context, {
      required String title,
      required int initialValue,
      required void Function(int value) onSubmit,
    }) {
      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (_) => ProfileTextInputSheet(
          title: title,
          buttonTitle: l10n.save,
          initialValue: initialValue.toString(),
          keyboardType: TextInputType.number,
          onSubmit: (value) {
            final parsed = int.tryParse(value);
            if (parsed == null) return;
            onSubmit(parsed);
          },
          sheetBackground: colors.surface,
          fieldBackground: isDark ? colors.surfaceAlt : colors.background,
          buttonBackground: isDark ? AppPalette.dark900 : AppPalette.blue900,
          buttonForeground: isDark ? colors.textPrimary : colors.textOnBrand,
          sheetRadius: dp(context, radii.r10),
          fieldHeight: fieldH,
          fieldRadius: fieldR,
          titleStyle: labelStyle,
          valueStyle: valueStyle,
          buttonStyle: TextStyle(
            fontFamily: text.family,
            fontSize: sp(context, text.fs20),
            fontWeight: text.w600,
            height: 1.0,
          ),
          shadow: shadows.card,
          space: space,
        ),
      );
    }

    return Scaffold(
      backgroundColor: colors.background,
      body: BlocBuilder<ProfileCubit, ProfileState>(
        builder: (context, state) {
          if (state is ProfileInitial) {
            context.read<ProfileCubit>().loadProfile();
          }
          if (state is ProfileLoading) {
            return const Center(child: CircularProgressIndicator());
          }
          if (state is! ProfileLoaded) {
            return const SizedBox.shrink();
          }

          final profile = state.profile;
          final displayedDob = formatDob(profile.age) ?? demoDob;
          final cardBg = colors.surface;

          final innerZoneBg = isDark ? cardBg : AppPalette.grey050;
          final innerZoneBorderColor = isDark
              ? AppPalette.dark800
              : colors.background;
          final segBg = isDark ? colors.surfaceAlt : colors.background;
          final segActiveBg = colors.surface;
          final segText = colors.textPrimary;

          final bottomPad =
              dp(context, space.s80) +
              MediaQuery.paddingOf(context).bottom +
              dp(context, space.s20);
          return Column(
            children: [
              Container(
                height: headerH,
                width: double.infinity,
                color: headerBg,
                padding: EdgeInsets.only(
                  left: side,
                  right: side,
                  top: headerTopInset + dp(context, space.s20),
                ),
                alignment: Alignment.centerLeft,
                child: Text(l10n.profile, style: titleStyle),
              ),
              Expanded(
                child: SingleChildScrollView(
                  padding: EdgeInsets.only(
                    left: side,
                    right: side,
                    top: pad12,
                    bottom: bottomPad,
                  ),
                  child: Column(
                    children: [
                      // ---- Аккаунт
                      ProfileSectionCard(
                        backgroundColor: cardBg,
                        borderRadius: cardR,
                        shadow: shadows.card,
                        padding: EdgeInsets.all(pad12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(l10n.account, style: sectionTitleStyle),
                            SizedBox(height: pad6),
                            Container(
                              width: double.infinity,
                              decoration: BoxDecoration(
                                color: innerZoneBg,
                                borderRadius: BorderRadius.circular(cardR),
                                border: isDark
                                    ? Border.all(
                                        color: innerZoneBorderColor,
                                        width: dp(context, space.s1),
                                      )
                                    : null,
                              ),
                              padding: EdgeInsets.symmetric(
                                horizontal: pad12,
                                vertical: pad10,
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    Localizations.localeOf(context).languageCode ==
                                            'ru'
                                        ? 'Облачная синхронизация пока недоступна.'
                                        : 'Cloud sync is not available yet.',
                                    style: valueStyle.copyWith(
                                      fontSize: sp(context, text.fs16),
                                      fontWeight: text.w500,
                                    ),
                                  ),
                                  SizedBox(height: pad6),
                                  Text(
                                    Localizations.localeOf(context).languageCode ==
                                            'ru'
                                        ? 'Все данные хранятся локально на устройстве.'
                                        : 'All data is stored locally on this device.',
                                    style: hintStyle,
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),

                      SizedBox(height: pad12),

                      // ---- Профиль
                      ProfileSectionCard(
                        backgroundColor: cardBg,
                        borderRadius: cardR,
                        shadow: shadows.card,
                        padding: EdgeInsets.all(pad12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(l10n.name, style: labelStyle),
                            SizedBox(height: pad6),
                            wideField(
                              textValue: profile.name.isEmpty
                                  ? 'Дмитрий'
                                  : profile.name,
                              onTap: () => showNameInputSheet(context, profile),
                            ),

                            SizedBox(height: pad10),

                            Row(
                              children: [
                                Expanded(
                                  child: Text(l10n.gender, style: labelStyle),
                                ),
                                SizedBox(width: dp(context, space.s20)),
                                Expanded(
                                  child: Align(
                                    alignment: Alignment.centerRight,
                                    child: Text(
                                      l10n.birthDate,
                                      style: labelStyle,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            SizedBox(height: pad6),
                            Row(
                              children: [
                                Expanded(
                                  child: Container(
                                    height: fieldH,
                                    decoration: BoxDecoration(
                                      color: segBg,
                                      borderRadius: BorderRadius.circular(
                                        fieldR,
                                      ),
                                    ),
                                    padding: EdgeInsets.all(pad4),
                                    child: Row(
                                      children: [
                                        segPill(
                                          title: l10n.male,
                                          selected: profile.gender == 'male',
                                          activeBg: segActiveBg,
                                          inactiveText: segText,
                                          activeText: segText,
                                          onTap: () => context
                                              .read<ProfileCubit>()
                                              .updateProfile(gender: 'male'),
                                        ),
                                        SizedBox(width: pad4),
                                        segPill(
                                          title: l10n.female,
                                          selected: profile.gender == 'female',
                                          activeBg: segActiveBg,
                                          inactiveText: segText,
                                          activeText: segText,
                                          onTap: () => context
                                              .read<ProfileCubit>()
                                              .updateProfile(gender: 'female'),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                                SizedBox(width: dp(context, space.s20)),
                                valueBox(
                                  textValue: displayedDob,
                                  onTap: () => pickDob(context, profile),
                                ),
                              ],
                            ),

                            SizedBox(height: pad10),

                            Text(l10n.pressureNorms, style: labelStyle),
                            SizedBox(height: pad6),
                            normsBlock(
                              topValue: profile.targetSystolic.toString(),
                              bottomValue: profile.targetDiastolic.toString(),
                              onTapTop: () => showIntInputSheet(
                                context,
                                title: l10n.upper,
                                initialValue: profile.targetSystolic,
                                onSubmit: (v) => context
                                    .read<ProfileCubit>()
                                    .updateProfile(targetSystolic: v),
                              ),
                              onTapBottom: () => showIntInputSheet(
                                context,
                                title: l10n.lower,
                                initialValue: profile.targetDiastolic,
                                onSubmit: (v) => context
                                    .read<ProfileCubit>()
                                    .updateProfile(targetDiastolic: v),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
