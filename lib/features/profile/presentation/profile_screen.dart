import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/theme/scale.dart';
import '../../../l10n/generated/app_localizations.dart';

import 'bloc/profile_cubit.dart';
import 'bloc/profile_state.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;

    final isDark = Theme.of(context).brightness == Brightness.dark;

    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final shadows = context.appShadow;
    final text = context.appText;

    final headerH = dp(context, space.s128);
    final side = dp(context, space.s20);

    final cardW = dp(context, space.w320);
    final cardR = dp(context, radii.r10);

    final innerW = cardW - dp(context, space.s24); // 296
    final fieldH = dp(context, space.s48);
    final fieldR = dp(context, radii.r10);

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final headerTopInset = MediaQuery.paddingOf(context).top;

    // UI-only: в макете показан пример даты
    const demoDob = '25.12.1980';

    // Плотнее по Y — главный фикс
    final pad12 = dp(context, space.s12);
    final pad10 = dp(context, space.s10);
    final pad8 = dp(context, space.s8);
    final pad6 = dp(context, space.s6);
    final pad4 = dp(context, space.s4);
    final pad2 = dp(context, space.s2);

    final titleStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs26),
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

    final privacyStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs12),
      fontWeight: text.w400,
      color: colors.textPrimary,
      height: 1.0,
    );

    Widget _primaryButton({
      required String title,
      String? subtitle,
      required Color bg,
      required Color fg,
      required VoidCallback onTap,
    }) {
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          height: fieldH,
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(fieldR),
          ),
          alignment: Alignment.center,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(
                title,
                style: TextStyle(
                  fontFamily: text.family,
                  fontSize: sp(context, text.fs20),
                  fontWeight: text.w600,
                  color: fg,
                  height: 1.0,
                ),
              ),
              if (subtitle != null && subtitle.isNotEmpty) ...[
                SizedBox(height: dp(context, space.s2)),
                Text(subtitle, style: hintStyle.copyWith(color: fg), textAlign: TextAlign.center),
              ],
            ],
          ),
        ),
      );
    }

    Widget _wideField({required String textValue}) {
      final bg = isDark ? colors.surfaceAlt : colors.background;
      return Container(
        height: fieldH,
        width: innerW,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(fieldR),
        ),
        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
        alignment: Alignment.centerLeft,
        child: Text(textValue, style: valueStyle),
      );
    }

    Widget _valueBox({required String textValue}) {
      final w = dp(context, space.s120 + space.s16 + space.s1); // 137
      final bg = isDark ? colors.surfaceAlt : colors.background;

      return Container(
        height: fieldH,
        width: w,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(fieldR),
        ),
        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
        alignment: Alignment.centerRight,
        child: Text(textValue, style: valueStyle),
      );
    }

    Widget _segPill({
      required String title,
      required bool selected,
      required VoidCallback onTap,
      required Color activeBg,
      required Color inactiveText,
      required Color activeText,
    }) {
      return Expanded(
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: onTap,
          child: Container(
            height: fieldH,
            decoration: BoxDecoration(
              color: selected ? activeBg : Colors.transparent,
              borderRadius: BorderRadius.circular(fieldR),
            ),
            alignment: Alignment.center,
            child: Text(
              title,
              style: valueStyle.copyWith(color: selected ? activeText : inactiveText),
            ),
          ),
        ),
      );
    }

    // ---- Нормы давления: правые поля как дата рождения, рамка 1px,
    // отступ до рамки 2px, левый текст чуть правее, расстояние между строками 4px
    Widget normsBlock({
      required String topValue,
      required String bottomValue,
    }) {
      final fieldBg = isDark ? colors.surfaceAlt : colors.background;
      final borderColor = fieldBg; // "цвет рамки как цвет у полей"
      final borderW = dp(context, space.s1);

      final labelLeftPad = dp(context, space.s12); // сдвиг вправо от рамки
      final betweenRows = pad4; // нужно 4px

      return Container(
        width: innerW,
        decoration: BoxDecoration(
          border: Border.all(color: borderColor, width: borderW),
          borderRadius: BorderRadius.circular(fieldR),
        ),
        padding: EdgeInsets.all(pad2), // 2px до рамки
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
                        child: Text('Верхнее', style: valueStyle),
                      ),
                    ),
                  ),
                  _valueBox(textValue: topValue),
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
                        child: Text('Нижнее', style: valueStyle),
                      ),
                    ),
                  ),
                  _valueBox(textValue: bottomValue),
                ],
              ),
            ),
          ],
        ),
      );
    }

    return Scaffold(
      backgroundColor: colors.background,
      body: BlocBuilder<ProfileCubit, ProfileState>(
        builder: (context, state) {
          if (state is ProfileLoading) {
            return const Center(child: CircularProgressIndicator());
          }
          if (state is! ProfileLoaded) {
            return const SizedBox.shrink();
          }

          final profile = state.profile;

          // Пока нет данных об аккаунте — считаем "не вошли" (как макет)
          const isLoggedIn = false;

          final cardBg = colors.surface;

          // Аккаунт: в dark средний блок с границей и тем же фоном, что внешняя карточка
          final innerZoneBg = isDark ? cardBg : AppPalette.grey050;
          final innerZoneBorderColor = isDark ? (isDark ? AppPalette.dark800 : colors.background) : Colors.transparent;

          // Кнопка Аккаунт: dark active как кнопки, inactive как поля профиля
          final accountBtnBg = isDark
              ? (isLoggedIn ? AppPalette.dark900 : colors.surfaceAlt)
              : (isLoggedIn ? AppPalette.blue900 : AppPalette.blue500);

          final accountBtnFg = isDark
              ? (isLoggedIn ? colors.textPrimary : colors.textPrimary)
              : colors.textOnBrand;

          final segBg = isDark ? colors.surfaceAlt : colors.background;
          final segActiveBg = colors.surface;
          final segText = colors.textPrimary;

          final bottomPad = dp(context, space.s80);

          return Column(
            children: [
              // Header: как на "Графики"
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
                      SizedBox(
                        width: cardW,
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            color: cardBg,
                            borderRadius: BorderRadius.circular(cardR),
                            boxShadow: [shadows.card],
                          ),
                          child: Padding(
                            padding: EdgeInsets.all(pad12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Аккаунт', style: sectionTitleStyle),
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
                                  padding: EdgeInsets.symmetric(horizontal: pad12, vertical: pad10),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text('Вы не вошли в аккаунт', style: hintStyle),
                                      SizedBox(height: pad8),
                                      Center(
                                        child: SizedBox(
                                          width: dp(context, space.w320 - space.s48), // 272
                                          child: _primaryButton(
                                            title: 'Войти',
                                            bg: accountBtnBg,
                                            fg: accountBtnFg,
                                            onTap: () {},
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),

                      SizedBox(height: pad12),

                      // ---- Профиль
                      SizedBox(
                        width: cardW,
                        child: DecoratedBox(
                          decoration: BoxDecoration(
                            color: cardBg,
                            borderRadius: BorderRadius.circular(cardR),
                            boxShadow: [shadows.card],
                          ),
                          child: Padding(
                            padding: EdgeInsets.all(pad12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text('Имя', style: labelStyle),
                                SizedBox(height: pad6),
                                _wideField(textValue: profile.name.isEmpty ? 'Дмитрий' : profile.name),

                                SizedBox(height: pad10),

                                Row(
                                  children: [
                                    Expanded(child: Text('Пол', style: labelStyle)),
                                    SizedBox(width: dp(context, space.s20)),
                                    Expanded(
                                      child: Align(
                                        alignment: Alignment.centerRight,
                                        child: Text('Дата рождения', style: labelStyle),
                                      ),
                                    ),
                                  ],
                                ),
                                SizedBox(height: pad6),
                                Row(
                                  children: [
                                    SizedBox(
                                      width: dp(context, (space.w320 - space.s40) / 2), // 140
                                      child: Container(
                                        height: fieldH,
                                        decoration: BoxDecoration(
                                          color: segBg,
                                          borderRadius: BorderRadius.circular(fieldR),
                                        ),
                                        padding: EdgeInsets.all(pad4),
                                        child: Row(
                                          children: [
                                            _segPill(
                                              title: 'Муж.',
                                              selected: profile.gender == 'male',
                                              activeBg: segActiveBg,
                                              inactiveText: segText,
                                              activeText: segText,
                                              onTap: () => context.read<ProfileCubit>().updateProfile(gender: 'male'),
                                            ),
                                            SizedBox(width: pad4),
                                            _segPill(
                                              title: 'Жен.',
                                              selected: profile.gender == 'female',
                                              activeBg: segActiveBg,
                                              inactiveText: segText,
                                              activeText: segText,
                                              onTap: () =>
                                                  context.read<ProfileCubit>().updateProfile(gender: 'female'),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                    const Spacer(),
                                    _valueBox(textValue: demoDob),
                                  ],
                                ),

                                SizedBox(height: pad10),

                                // ---- Нормы давления
                                Text('Нормы давления', style: labelStyle),
                                SizedBox(height: pad6),
                                normsBlock(
                                  topValue: profile.targetSystolic.toString(),
                                  bottomValue: profile.targetDiastolic.toString(),
                                ),

                                SizedBox(height: pad12),

                                Center(
                                  child: SizedBox(
                                    width: dp(context, space.w320 - space.s48), // 272
                                    child: _primaryButton(
                                      title: 'Убрать рекламу',
                                      subtitle: 'Разовый платеж 2,99 € -  навсегда',
                                      bg: isDark ? AppPalette.dark900 : AppPalette.blue900,
                                      fg: isDark ? colors.textPrimary : colors.textOnBrand,
                                      onTap: () {},
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ),

                      SizedBox(height: pad12),
                      Text('Политика конфиденциальности', style: privacyStyle, textAlign: TextAlign.center),
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
