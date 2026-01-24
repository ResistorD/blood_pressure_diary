import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/theme/scale.dart';
import '../../../l10n/generated/app_localizations.dart';

import 'bloc/profile_cubit.dart';
import 'bloc/profile_state.dart';

class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});

  String _providerTitle(String provider) {
    switch (provider) {
      case 'google':
        return 'Google';
      case 'apple':
        return 'Apple';
      case 'email':
        return 'Email';
      default:
        return provider.isEmpty ? 'Аккаунт' : provider;
    }
  }

  int _birthDateToStorage(DateTime date) {
    return date.year * 10000 + date.month * 100 + date.day;
  }

  DateTime? _birthDateFromStorage(int raw) {
    if (raw < 10000101) return null;
    final year = raw ~/ 10000;
    final month = (raw % 10000) ~/ 100;
    final day = raw % 100;
    if (month < 1 || month > 12) return null;
    final lastDay = DateTime(year, month + 1, 0).day;
    if (day < 1 || day > lastDay) return null;
    return DateTime(year, month, day);
  }

  String _formatBirthDate(int raw) {
    final date = _birthDateFromStorage(raw);
    if (date == null) return '—';
    return DateFormat('dd.MM.yyyy').format(date);
  }

  String _formatWeight(double weight) {
    if (weight <= 0) return '—';
    if (weight % 1 == 0) {
      return weight.toStringAsFixed(0);
    }
    return weight.toStringAsFixed(1);
  }

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

    Widget _wideField({required String textValue, VoidCallback? onTap}) {
      final bg = isDark ? colors.surfaceAlt : colors.background;
      final content = Container(
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

      if (onTap == null) return content;

      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: content,
      );
    }

    Widget _valueBox({required String textValue, VoidCallback? onTap}) {
      final w = dp(context, space.s120 + space.s16 + space.s1); // 137
      final bg = isDark ? colors.surfaceAlt : colors.background;

      final content = Container(
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

      if (onTap == null) return content;

      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: content,
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

    Widget normsBlock({
      required String topValue,
      required String bottomValue,
      required VoidCallback onTap,
    }) {
      final fieldBg = isDark ? colors.surfaceAlt : colors.background;
      final borderColor = fieldBg;
      final borderW = dp(context, space.s1);

      final labelLeftPad = dp(context, space.s12);
      final betweenRows = pad4;

      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          width: innerW,
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
        ),
      );
    }

    Widget _sheetItem({
      required BuildContext context,
      required String title,
      required VoidCallback onTap,
    }) {
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          height: fieldH,
          decoration: BoxDecoration(
            color: isDark ? colors.surfaceAlt : colors.background,
            borderRadius: BorderRadius.circular(fieldR),
          ),
          padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
          alignment: Alignment.centerLeft,
          child: Text(title, style: valueStyle),
        ),
      );
    }

    void _showSingleFieldSheet({
      required BuildContext context,
      required String title,
      required String initialValue,
      required TextInputType inputType,
      required String actionTitle,
      required ValueChanged<String> onSave,
    }) {
      final controller = TextEditingController(text: initialValue);

      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (ctx) {
          final sheetBg = colors.surface;
          final sheetR = dp(context, radii.r10);
          final bottomInset = MediaQuery.viewInsetsOf(ctx).bottom;

          return SafeArea(
            child: Padding(
              padding: EdgeInsets.only(
                left: dp(context, space.s12),
                right: dp(context, space.s12),
                bottom: dp(context, space.s12) + bottomInset,
              ),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: sheetBg,
                  borderRadius: BorderRadius.circular(sheetR),
                  boxShadow: [shadows.card],
                ),
                child: Padding(
                  padding: EdgeInsets.all(dp(context, space.s12)),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title, style: sectionTitleStyle),
                      SizedBox(height: dp(context, space.s8)),
                      Container(
                        height: fieldH,
                        decoration: BoxDecoration(
                          color: isDark ? colors.surfaceAlt : colors.background,
                          borderRadius: BorderRadius.circular(fieldR),
                        ),
                        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
                        alignment: Alignment.centerLeft,
                        child: TextField(
                          controller: controller,
                          keyboardType: inputType,
                          decoration: const InputDecoration(
                            border: InputBorder.none,
                            isCollapsed: true,
                          ),
                          style: valueStyle,
                        ),
                      ),
                      SizedBox(height: dp(context, space.s12)),
                      SizedBox(
                        width: double.infinity,
                        child: _primaryButton(
                          title: actionTitle,
                          bg: isDark ? AppPalette.dark900 : AppPalette.blue900,
                          fg: isDark ? colors.textPrimary : colors.textOnBrand,
                          onTap: () {
                            final value = controller.text.trim();
                            if (value.isEmpty) return;
                            onSave(value);
                            Navigator.pop(ctx);
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      );
    }

    void _showNormsSheet({
      required BuildContext context,
      required int systolic,
      required int diastolic,
      required ValueChanged<Map<String, int>> onSave,
    }) {
      final sysController = TextEditingController(text: systolic.toString());
      final diaController = TextEditingController(text: diastolic.toString());

      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (ctx) {
          final sheetBg = colors.surface;
          final sheetR = dp(context, radii.r10);
          final bottomInset = MediaQuery.viewInsetsOf(ctx).bottom;

          Widget inputField(TextEditingController controller) {
            return Container(
              height: fieldH,
              decoration: BoxDecoration(
                color: isDark ? colors.surfaceAlt : colors.background,
                borderRadius: BorderRadius.circular(fieldR),
              ),
              padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
              alignment: Alignment.centerLeft,
              child: TextField(
                controller: controller,
                keyboardType: TextInputType.number,
                decoration: const InputDecoration(
                  border: InputBorder.none,
                  isCollapsed: true,
                ),
                style: valueStyle,
              ),
            );
          }

          return SafeArea(
            child: Padding(
              padding: EdgeInsets.only(
                left: dp(context, space.s12),
                right: dp(context, space.s12),
                bottom: dp(context, space.s12) + bottomInset,
              ),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: sheetBg,
                  borderRadius: BorderRadius.circular(sheetR),
                  boxShadow: [shadows.card],
                ),
                child: Padding(
                  padding: EdgeInsets.all(dp(context, space.s12)),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Нормы давления', style: sectionTitleStyle),
                      SizedBox(height: dp(context, space.s8)),
                      inputField(sysController),
                      SizedBox(height: dp(context, space.s8)),
                      inputField(diaController),
                      SizedBox(height: dp(context, space.s12)),
                      SizedBox(
                        width: double.infinity,
                        child: _primaryButton(
                          title: 'Сохранить',
                          bg: isDark ? AppPalette.dark900 : AppPalette.blue900,
                          fg: isDark ? colors.textPrimary : colors.textOnBrand,
                          onTap: () {
                            final sysValue = int.tryParse(sysController.text.trim());
                            final diaValue = int.tryParse(diaController.text.trim());
                            if (sysValue == null || diaValue == null) return;
                            onSave({'sys': sysValue, 'dia': diaValue});
                            Navigator.pop(ctx);
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      );
    }

    void _showEmailInputSheet(BuildContext context) {
      final controller = TextEditingController();

      showModalBottomSheet(
        context: context,
        isScrollControlled: true,
        backgroundColor: Colors.transparent,
        builder: (ctx) {
          final sheetBg = colors.surface;
          final sheetR = dp(context, radii.r10);
          final bottomInset = MediaQuery.viewInsetsOf(ctx).bottom;

          return SafeArea(
            child: Padding(
              padding: EdgeInsets.only(
                left: dp(context, space.s12),
                right: dp(context, space.s12),
                bottom: dp(context, space.s12) + bottomInset,
              ),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: sheetBg,
                  borderRadius: BorderRadius.circular(sheetR),
                  boxShadow: [shadows.card],
                ),
                child: Padding(
                  padding: EdgeInsets.all(dp(context, space.s12)),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Email', style: sectionTitleStyle),
                      SizedBox(height: dp(context, space.s8)),
                      Container(
                        height: fieldH,
                        decoration: BoxDecoration(
                          color: isDark ? colors.surfaceAlt : colors.background,
                          borderRadius: BorderRadius.circular(fieldR),
                        ),
                        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
                        alignment: Alignment.centerLeft,
                        child: TextField(
                          controller: controller,
                          keyboardType: TextInputType.emailAddress,
                          decoration: const InputDecoration(
                            border: InputBorder.none,
                            isCollapsed: true,
                          ),
                          style: valueStyle,
                        ),
                      ),
                      SizedBox(height: dp(context, space.s12)),
                      SizedBox(
                        width: double.infinity,
                        child: _primaryButton(
                          title: 'Подключить',
                          bg: isDark ? AppPalette.dark900 : AppPalette.blue900,
                          fg: isDark ? colors.textPrimary : colors.textOnBrand,
                          onTap: () {
                            final email = controller.text.trim();
                            if (email.isEmpty) return;
                            context.read<ProfileCubit>().linkAccount(provider: 'email', email: email);
                            Navigator.pop(ctx);
                          },
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      );
    }

    void _showAccountLinkSheet(BuildContext context) {
      showModalBottomSheet(
        context: context,
        backgroundColor: Colors.transparent,
        builder: (ctx) {
          final sheetBg = colors.surface;
          final sheetR = dp(context, radii.r10);

          return SafeArea(
            child: Padding(
              padding: EdgeInsets.all(dp(context, space.s12)),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: sheetBg,
                  borderRadius: BorderRadius.circular(sheetR),
                  boxShadow: [shadows.card],
                ),
                child: Padding(
                  padding: EdgeInsets.all(dp(context, space.s12)),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Выберите способ входа', style: sectionTitleStyle),
                      SizedBox(height: dp(context, space.s12)),
                      _sheetItem(
                        context: context,
                        title: 'Email',
                        onTap: () {
                          Navigator.pop(ctx);
                          _showEmailInputSheet(context);
                        },
                      ),
                      SizedBox(height: dp(context, space.s8)),
                      _sheetItem(
                        context: context,
                        title: 'Google',
                        onTap: () {
                          // локальная привязка: провайдер есть, email пустой
                          context.read<ProfileCubit>().linkAccount(provider: 'google', email: '');
                          Navigator.pop(ctx);
                        },
                      ),
                      SizedBox(height: dp(context, space.s8)),
                      _sheetItem(
                        context: context,
                        title: 'Apple',
                        onTap: () {
                          context.read<ProfileCubit>().linkAccount(provider: 'apple', email: '');
                          Navigator.pop(ctx);
                        },
                      ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
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
          final isLoggedIn = profile.accountLinked;

          final cardBg = colors.surface;

          final innerZoneBg = isDark ? cardBg : AppPalette.grey050;
          final innerZoneBorderColor = isDark ? AppPalette.dark800 : colors.background;

          final accountBtnBg = isDark
              ? (isLoggedIn ? colors.surfaceAlt : AppPalette.dark900)
              : (isLoggedIn ? AppPalette.blue500 : AppPalette.blue900);

          final accountBtnFg = isDark ? colors.textPrimary : colors.textOnBrand;

          final segBg = isDark ? colors.surfaceAlt : colors.background;
          final segActiveBg = colors.surface;
          final segText = colors.textPrimary;

          final bottomPad = dp(context, space.s80);

          final accountLine = profile.accountEmail.trim().isNotEmpty
              ? profile.accountEmail.trim()
              : _providerTitle(profile.accountProvider);

          final nameValue = profile.name.isEmpty ? 'Дмитрий' : profile.name;
          final weightValue = _formatWeight(profile.weight);
          final birthDateValue = _formatBirthDate(profile.age);

          Future<void> pickBirthDate() async {
            final initial = _birthDateFromStorage(profile.age) ?? DateTime.now();
            final picked = await showDatePicker(
              context: context,
              initialDate: initial,
              firstDate: DateTime(1900),
              lastDate: DateTime.now(),
            );
            if (picked == null) return;
            context.read<ProfileCubit>().updateProfile(age: _birthDateToStorage(picked));
          }

          void openNameSheet() {
            _showSingleFieldSheet(
              context: context,
              title: 'Имя',
              initialValue: profile.name,
              inputType: TextInputType.name,
              actionTitle: 'Сохранить',
              onSave: (value) => context.read<ProfileCubit>().updateProfile(name: value),
            );
          }

          void openWeightSheet() {
            _showSingleFieldSheet(
              context: context,
              title: 'Вес',
              initialValue: profile.weight == 0 ? '' : profile.weight.toString(),
              inputType: const TextInputType.numberWithOptions(decimal: true),
              actionTitle: 'Сохранить',
              onSave: (value) {
                final normalized = value.replaceAll(',', '.');
                final parsed = double.tryParse(normalized);
                if (parsed == null) return;
                context.read<ProfileCubit>().updateProfile(weight: parsed);
              },
            );
          }

          void openNormsSheet() {
            _showNormsSheet(
              context: context,
              systolic: profile.targetSystolic,
              diastolic: profile.targetDiastolic,
              onSave: (values) {
                context.read<ProfileCubit>().updateProfile(
                  targetSystolic: values['sys'],
                  targetDiastolic: values['dia'],
                );
              },
            );
          }

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
                                      if (!isLoggedIn) ...[
                                        Text('Вы не вошли в аккаунт', style: hintStyle),
                                        SizedBox(height: pad8),
                                        Center(
                                          child: SizedBox(
                                            width: dp(context, space.w320 - space.s48), // 272
                                            child: _primaryButton(
                                              title: 'Войти',
                                              bg: accountBtnBg,
                                              fg: accountBtnFg,
                                              onTap: () => _showAccountLinkSheet(context),
                                            ),
                                          ),
                                        ),
                                      ] else ...[
                                        Text('Аккаунт подключен', style: hintStyle),
                                        SizedBox(height: pad4),
                                        Text(accountLine, style: valueStyle),
                                        SizedBox(height: pad8),
                                        Center(
                                          child: SizedBox(
                                            width: dp(context, space.w320 - space.s48), // 272
                                            child: _primaryButton(
                                              title: 'Выйти',
                                              bg: accountBtnBg,
                                              fg: accountBtnFg,
                                              onTap: () => context.read<ProfileCubit>().unlinkAccount(),
                                            ),
                                          ),
                                        ),
                                      ],
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
                                _wideField(textValue: nameValue, onTap: openNameSheet),

                                SizedBox(height: pad10),

                                Text('Вес', style: labelStyle),
                                SizedBox(height: pad6),
                                _wideField(textValue: weightValue, onTap: openWeightSheet),

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
                                              onTap: () => context.read<ProfileCubit>().updateProfile(gender: 'female'),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                    const Spacer(),
                                    _valueBox(textValue: birthDateValue, onTap: pickBirthDate),
                                  ],
                                ),

                                SizedBox(height: pad10),

                                Text('Нормы давления', style: labelStyle),
                                SizedBox(height: pad6),
                                normsBlock(
                                  topValue: profile.targetSystolic.toString(),
                                  bottomValue: profile.targetDiastolic.toString(),
                                  onTap: openNormsSheet,
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
