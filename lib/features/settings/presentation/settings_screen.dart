import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'package:blood_pressure_diary/core/services/export_service.dart';
import 'package:blood_pressure_diary/core/services/backup_service.dart';
import 'package:blood_pressure_diary/core/database/isar_service.dart';
import 'package:blood_pressure_diary/core/di/service_locator.dart';
import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/core/theme/scale.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_cubit.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_state.dart';
import 'package:blood_pressure_diary/features/settings/presentation/privacy_policy_screen.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';

import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:file_picker/file_picker.dart';

import '../data/models/settings_model.dart';

enum _DayPeriod { morning, day, evening, night }

bool _isTimeInPeriod(TimeOfDay t, _DayPeriod p) {
  final minutes = t.hour * 60 + t.minute;

  bool inRange(int startH, int endH) {
    final start = startH * 60;
    final end = endH * 60;
    if (start <= end) return minutes >= start && minutes < end;
    // wrap-around (e.g. 22–06)
    return minutes >= start || minutes < end;
  }

  switch (p) {
    case _DayPeriod.morning:
      return inRange(6, 10);
    case _DayPeriod.day:
      return inRange(12, 16);
    case _DayPeriod.evening:
      return inRange(18, 22);
    case _DayPeriod.night:
      return inRange(22, 6);
  }
}

TimeOfDay _initialTimeForPeriod(_DayPeriod p) {
  switch (p) {
    case _DayPeriod.morning:
      return const TimeOfDay(hour: 8, minute: 0);
    case _DayPeriod.day:
      return const TimeOfDay(hour: 14, minute: 0);
    case _DayPeriod.evening:
      return const TimeOfDay(hour: 20, minute: 0);
    case _DayPeriod.night:
      return const TimeOfDay(hour: 23, minute: 0);
  }
}

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  String _tr(BuildContext context, String ru, String en) {
    final lang = Localizations.localeOf(context).languageCode.toLowerCase();
    return lang.startsWith('ru') ? ru : en;
  }

  double _contentBottomInset(BuildContext context) {
    final s = context.appSpace;
    final safeBottom = MediaQuery.paddingOf(context).bottom;
    // Bottom bar in AppNavigation: barH (69) + lift (43) = 112 (tokens-based)
    final barH = dp(context, s.s72 - s.s2 - s.s1);
    final outer = dp(context, s.s80 + s.s6);
    final lift = outer / 2;
    return barH + safeBottom + dp(context, s.s8);
  }

  Future<void> _runBlocking(BuildContext context, Future<void> Function() action) async {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    try {
      await action();
    } finally {
      if (context.mounted) Navigator.pop(context);
    }
  }

  Future<void> _backupToJson(BuildContext context) async {
    final isar = getIt<IsarService>();
    final backupService = BackupService(isar);

    await _runBlocking(context, () async {
      final json = await backupService.createBackupJson();

      final dir = await getTemporaryDirectory();
      final ts = DateTime.now().toIso8601String().replaceAll(':', '-');
      final file = File('${dir.path}/pressure_diary_backup_$ts.json');
      await file.writeAsString(json, flush: true);

      await Share.shareXFiles(
        [XFile(file.path)],
        text: 'Pressure Diary backup (JSON)',
      );
    });
  }

  Future<void> _restoreFromJson(BuildContext context) async {
    final isar = getIt<IsarService>();
    final backupService = BackupService(isar);

    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: const ['json'],
      withData: false,
    );

    if (result == null || result.files.isEmpty) return;
    final path = result.files.first.path;
    if (path == null) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: Text(_tr(context, 'Восстановление из копии', 'Restore from backup')),
        content: Text(_tr(context, 'Это действие заменит все текущие данные приложения (профиль, настройки и записи давления). Продолжить?', 'This will replace all current app data (profile, settings, and measurements). Continue?')),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(_tr(context, 'Отмена', 'Cancel'))),
          TextButton(onPressed: () => Navigator.pop(context, true), child: Text(_tr(context, 'Восстановить', 'Restore'))),
        ],
      ),
    );

    if (confirmed != true) return;

    await _runBlocking(context, () async {
      final jsonText = await File(path).readAsString();
      await backupService.restoreFromJson(jsonText);
    });

    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(_tr(context, 'Данные восстановлены', 'Data restored'))),
    );
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

    final safeTop = MediaQuery.paddingOf(context).top;

    final headerH = dp(context, space.s128);
    final side = dp(context, space.s20);

    final cardW = dp(context, space.w320);
    final innerW = cardW - dp(context, space.s24); // 296
    final cardR = dp(context, radii.r10);

    final fieldH = dp(context, space.s48);

    final h47 = dp(context, space.s46 + space.s1); // 47
    final h92 = dp(context, space.s80 + space.s12); // 92

    final h43 = dp(context, space.s40 + space.s2 + space.s1);
    final h44 = dp(context, space.s40 + space.s4);

    // ---- Required vertical gaps (6 total)
    final gap16 = dp(context, space.s16);
    final gap8 = dp(context, space.s8);

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final titleColor = isDark ? colors.textPrimary : colors.textOnBrand;

    final cardBg = colors.surface;
    final fieldBg = isDark ? colors.surfaceAlt : colors.background;

    final trackOn = isDark ? AppPalette.dark800 : AppPalette.blue900;
    final trackOff = isDark ? AppPalette.dark800 : AppPalette.grey200;
    final knobOn = isDark ? AppPalette.dark400 : colors.surface;
    final knobOff = isDark ? AppPalette.dark400 : colors.surface;

    final overlayColor = colors.textPrimary.withValues(alpha: 0.10);

    final titleStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs24),
      fontWeight: text.w600,
      color: titleColor,
      height: 1.0,
    );

    final cardTitleStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs20),
      fontWeight: text.w600,
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

    final itemStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs20),
      fontWeight: text.w500,
      color: colors.textPrimary,
      height: 1.0,
    );

    final addStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs16),
      fontWeight: text.w600,
      color: colors.textPrimary,
      height: 1.0,
    );

    final versionStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs12),
      fontWeight: text.w400,
      color: colors.textPrimary,
      height: 1.0,
    );

    Future<TimeOfDay?> _pickTimeInput(BuildContext context, {TimeOfDay? initialTime}) {
      return showTimePicker(
        context: context,
        initialTime: initialTime ?? TimeOfDay.now(),
        initialEntryMode: TimePickerEntryMode.input,
        builder: (ctx, child) {
          return MediaQuery(
            data: MediaQuery.of(ctx).copyWith(alwaysUse24HourFormat: true),
            child: child ?? const SizedBox.shrink(),
          );
        },
      );
    }


    return BlocListener<SettingsCubit, SettingsState>(
      listener: (context, state) {
        final msg = state.errorMessage;
        if (msg == null) return;

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(msg),
            backgroundColor: colors.danger,
          ),
        );
      },
      child: BlocBuilder<SettingsCubit, SettingsState>(
        builder: (context, state) {
          final s = state.settings;
          final enabled = s.notificationsEnabled;

          Future<void> ensureDefaultRemindersPersisted() async {
            // UI shows 2 default reminders (08:00 / 20:00) when the list is empty.
            // Persist them on first interaction so that add/remove/edit works consistently.
            if (s.reminders.isNotEmpty || !context.mounted) return;
            final cubit = context.read<SettingsCubit>();
            await cubit.addReminder(const TimeOfDay(hour: 8, minute: 0));
            if (context.mounted) {
              await cubit.addReminder(const TimeOfDay(hour: 20, minute: 0));
            }
          }

          Future<void> pickAndAddTime() async {
            final picked = await _pickTimeInput(context);
            if (picked == null || !context.mounted) return;

            await ensureDefaultRemindersPersisted();
            if (!context.mounted) return;

            context.read<SettingsCubit>().addReminder(picked);
          }



          Future<void> pickReplaceAt(int index) async {
            final picked = await _pickTimeInput(context);
            if (picked == null || !context.mounted) return;

            await ensureDefaultRemindersPersisted();

            if (s.reminders.length > index) {
              await context.read<SettingsCubit>().removeReminder(index);
            }
            if (context.mounted) {
              context.read<SettingsCubit>().addReminder(picked);
            }
          }

          void removeAt(int index) {
            if (index < 0) return;
            ensureDefaultRemindersPersisted().then((_) {
              if (!context.mounted) return;
              final curr = context.read<SettingsCubit>().state.settings.reminders;
              if (index >= curr.length) return;
              context.read<SettingsCubit>().removeReminder(index);
            });
          }

          Widget cardAuto({required Widget child}) {
            return SizedBox(
              width: cardW,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: cardBg,
                  borderRadius: BorderRadius.circular(cardR),
                  boxShadow: [shadows.card],
                ),
                child: child,
              ),
            );
          }

          Widget cardFixed({required double height, required Widget child}) {
            return SizedBox(
              width: cardW,
              height: height,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: cardBg,
                  borderRadius: BorderRadius.circular(cardR),
                  boxShadow: [shadows.card],
                ),
                child: child,
              ),
            );
          }

          Widget timeValueBox({required String value, required double height}) {
            return Container(
              width: dp(context, space.s120 + space.s16 + space.s1), // 137
              height: height,
              decoration: BoxDecoration(
                color: fieldBg,
                borderRadius: BorderRadius.circular(cardR),
              ),
              padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
              alignment: Alignment.centerRight,
              child: Text(value, style: itemStyle),
            );
          }

          Widget minusButton({
            required double rowHeight,
            required VoidCallback onTap,
          }) {
            final hit = dp(context, space.s32); // 32
            final iconSize = dp(context, space.s20);
            final bg = fieldBg.withValues(alpha: 0.60);
            final fg = colors.textPrimary;

            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onTap,
              child: SizedBox(
                width: hit,
                height: rowHeight,
                child: Center(
                  child: Container(
                    width: hit,
                    height: hit,
                    decoration: BoxDecoration(
                      color: bg,
                      borderRadius: BorderRadius.circular(dp(context, space.s6)),
                    ),
                    child: Icon(
                      Icons.remove_circle_outline,
                      size: iconSize,
                      color: fg,
                    ),
                  ),
                ),
              ),
            );
          }

          Widget remindersInnerBox() {
            final borderColor = fieldBg;
            final borderW = dp(context, space.s1);

            final labelLeftPad = dp(context, space.s12);
            final betweenRows = dp(context, space.s4);
            final betweenMinusAndField = dp(context, space.s6);

            TimeOfDay? _parseTime(String v) {
              final parts = v.split(':');
              if (parts.length != 2) return null;
              final h = int.tryParse(parts[0]);
              final m = int.tryParse(parts[1]);
              if (h == null || m == null) return null;
              if (h < 0 || h > 23 || m < 0 || m > 59) return null;
              return TimeOfDay(hour: h, minute: m);
            }

            _DayPeriod _periodForTime(TimeOfDay t) {
              final minutes = t.hour * 60 + t.minute;

              bool inRange(int startH, int endH) {
                final start = startH * 60;
                final end = endH * 60;
                if (start <= end) return minutes >= start && minutes < end;
                // wrap-around (e.g. 22–06)
                return minutes >= start || minutes < end;
              }

              if (inRange(6, 10)) return _DayPeriod.morning;
              if (inRange(12, 16)) return _DayPeriod.day;
              if (inRange(18, 22)) return _DayPeriod.evening;
              return _DayPeriod.night;
            }

            String _labelForTimeValue(String v) {
              final t = _parseTime(v);
              if (t == null) return _tr(context, 'Время', 'Time');

              switch (_periodForTime(t)) {
                case _DayPeriod.morning:
                  return _tr(context, 'Утро', 'Morning');
                case _DayPeriod.day:
                  return _tr(context, 'День', 'Day');
                case _DayPeriod.evening:
                  return _tr(context, 'Вечер', 'Evening');
                case _DayPeriod.night:
                  return _tr(context, 'Ночь', 'Night');
              }
            }


            double rowHeightForIndex(int i) => i == 0 ? h43 : h44;

            Widget row({
              required int index,
              required String label,
              required String value,
              required double h,
            }) {
              // Morning (index 0) is fixed; evening (index 1) and further can be removed.
              final removable = index >= 1;

              return SizedBox(
                height: h,
                child: Row(
                  children: [
                    Expanded(
                      child: Padding(
                        padding: EdgeInsets.only(left: labelLeftPad),
                        child: Align(
                          alignment: Alignment.centerLeft,
                          child: Text(label, style: itemStyle),
                        ),
                      ),
                    ),
                    if (removable) ...[
                      minusButton(rowHeight: h, onTap: () => removeAt(index)),
                      SizedBox(width: betweenMinusAndField),
                    ],
                    GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => pickReplaceAt(index),
                      child: timeValueBox(value: value, height: h),
                    ),
                  ],
                ),
              );
            }

            return Opacity(
              opacity: enabled ? 1.0 : 0.55,
              child: Container(
                width: innerW,
                decoration: BoxDecoration(
                  border: Border.all(color: borderColor, width: borderW),
                  borderRadius: BorderRadius.circular(cardR),
                ),
                padding: EdgeInsets.all(dp(context, space.s2)),
                child: Column(
                  children: [
                    if (s.reminders.isEmpty) ...[
                      row(index: 0, label: _tr(context, 'Утро', 'Morning'), value: '08:00', h: h43),
                      SizedBox(height: betweenRows),
                      row(index: 1, label: _tr(context, 'Вечер', 'Evening'), value: '20:00', h: h44),
                    ] else ...[
                      for (int i = 0; i < s.reminders.length; i++) ...[
                        row(
                          index: i,
                          label: _labelForTimeValue(s.reminders[i]),
                          value: s.reminders[i],
                          h: rowHeightForIndex(i),
                        ),
                        if (i != s.reminders.length - 1) SizedBox(height: betweenRows),
                      ],
                    ],
                  ],
                ),
              ),
            );
          }

          Widget remindersCard() {
            return cardAuto(
              child: Padding(
                padding: EdgeInsets.all(dp(context, space.s12)),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    SizedBox(
                      height: dp(context, space.s24),
                      child: Row(
                        children: [
                          Expanded(
                            child: Align(
                              alignment: Alignment.centerLeft,
                              child: Text(l10n.reminders, style: cardTitleStyle),
                            ),
                          ),
                          _FigmaSwitch(
                            value: enabled,
                            onChanged: (v) => context.read<SettingsCubit>().toggleNotifications(v),
                            trackOn: trackOn,
                            trackOff: trackOff,
                            knobOn: knobOn,
                            knobOff: knobOff,
                            space: space,
                          ),
                        ],
                      ),
                    ),
                    SizedBox(height: dp(context, space.s10)),
                    remindersInnerBox(),
                    SizedBox(height: dp(context, space.s10)),
                    Align(
                      alignment: Alignment.centerRight,
                      child: Opacity(
                        opacity: enabled ? 1.0 : 0.55,
                        child: GestureDetector(
                          behavior: HitTestBehavior.opaque,
                          onTap: pickAndAddTime,
                          child: Padding(
                            padding: EdgeInsets.only(right: dp(context, space.s6)),
                            child: Text('+${l10n.addReminder.toUpperCase()}', style: addStyle),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            );
          }

          Widget themeCard() {
            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () async {
                final chosen = await _showThemeSheet(context, l10n, s.themeMode);
                if (chosen != null && context.mounted) {
                  context.read<SettingsCubit>().setThemeMode(chosen);
                }
              },
              child: cardFixed(
                height: h92,
                child: Padding(
                  padding: EdgeInsets.all(dp(context, space.s12)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l10n.theme, style: labelStyle),
                      SizedBox(height: dp(context, space.s6)),
                      Container(
                        width: innerW,
                        height: fieldH,
                        decoration: BoxDecoration(
                          color: fieldBg,
                          borderRadius: BorderRadius.circular(cardR),
                        ),
                        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
                        child: Row(
                          children: [
                            Expanded(child: Text(_themeTitle(s.themeMode, l10n), style: itemStyle)),
                            Icon(
                              Icons.keyboard_arrow_down,
                              color: colors.textPrimary,
                              size: dp(context, space.s20),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }


          Widget languageCard() {
            String titleFor(String code) {
              switch (code) {
                case 'ru':
                  return 'Русский';
                case 'en':
                  return 'English';
                default:
                  return code;
              }
            }

            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () async {
                final chosen = await _showLanguageSheet(context, l10n, s.languageCode);
                if (chosen != null && context.mounted) {
                  context.read<SettingsCubit>().changeLanguage(chosen);
                }
              },
              child: cardFixed(
                height: h92,
                child: Padding(
                  padding: EdgeInsets.all(dp(context, space.s12)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(l10n.language, style: labelStyle),
                      SizedBox(height: dp(context, space.s6)),
                      Container(
                        width: innerW,
                        height: fieldH,
                        decoration: BoxDecoration(
                          color: fieldBg,
                          borderRadius: BorderRadius.circular(cardR),
                        ),
                        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
                        child: Row(
                          children: [
                            Expanded(child: Text(titleFor(s.languageCode), style: itemStyle)),
                            Icon(
                              Icons.keyboard_arrow_down,
                              color: colors.textPrimary,
                              size: dp(context, space.s20),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          }

          Widget actionButton({required String title, required VoidCallback onTap}) {
            return GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: onTap,
              child: SizedBox(
                width: cardW,
                height: h47,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: cardBg,
                    borderRadius: BorderRadius.circular(cardR),
                    boxShadow: [shadows.card],
                  ),
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: dp(context, space.s16)),
                    child: Align(
                      alignment: Alignment.centerLeft,
                      child: Text(title, style: itemStyle),
                    ),
                  ),
                ),
              ),
            );
          }

          return Scaffold(
            backgroundColor: colors.background,
            body: Stack(
              children: [
                Positioned(
                  left: 0,
                  right: 0,
                  top: 0,
                  height: headerH,
                  child: Container(
                    decoration: BoxDecoration(
                      color: headerBg,
                      boxShadow: [shadows.strong],
                    ),
                    padding: EdgeInsets.only(
                      left: side,
                      right: side,
                      top: safeTop + dp(context, space.s20),
                    ),
                    alignment: Alignment.centerLeft,
                    child: Text(l10n.settings, style: titleStyle),
                  ),
                ),

                Positioned.fill(
                  top: safeTop + headerH - dp(context, space.s20),
                  child: SingleChildScrollView(
                    padding: EdgeInsets.only(
                      left: side,
                      right: side,
                      top: gap16,
                      bottom: _contentBottomInset(context),
                    ),
                    child: Column(
                      children: [
                        remindersCard(),
                        SizedBox(height: gap16),
                        themeCard(),
                        SizedBox(height: gap16),
                        languageCard(),
                        SizedBox(height: gap16),

                        actionButton(title: _tr(context, 'Резервная копия (JSON)', 'Backup (JSON)'), onTap: () => _backupToJson(context)),
                        SizedBox(height: gap8),
                        actionButton(title: _tr(context, 'Восстановить из копии', 'Restore from backup'), onTap: () => _restoreFromJson(context)),
                        SizedBox(height: gap8),

                        actionButton(title: l10n.clearData, onTap: () => _showClearDataDialog(context, l10n)),
                        SizedBox(height: gap8),
                        actionButton(
                          title: '${l10n.export} (CSV, PDF)',
                          onTap: state.isExporting ? () {} : () => _showExportBottomSheet(context, l10n),
                        ),
                        SizedBox(height: gap8),
                        actionButton(
                          title: l10n.contactSupport,
                          onTap: () => context.read<SettingsCubit>().contactSupport(),
                        ),
                        SizedBox(height: gap8),
                        actionButton(title: l10n.rateApp, onTap: () => context.read<SettingsCubit>().rateApp()),
                        SizedBox(height: gap8),
                        actionButton(
                          title: l10n.privacyPolicy,
                          onTap: () {
                            Navigator.of(context).push(
                              MaterialPageRoute(builder: (_) => const PrivacyPolicyScreen()),
                            );
                          },
                        ),
                        Padding(
                          padding: EdgeInsets.only(top: gap16),
                          child: Center(
                            child: Text(
                              '${l10n.versionLabel} ${state.appVersion ?? '—'}',
                              style: versionStyle,
                            ),
                          ),
                        ),

                        SizedBox(height: gap16),
                      ],
                    ),
                  ),
                ),
                if (state.isExporting)
                  Positioned.fill(
                    child: ColoredBox(
                      color: overlayColor,
                      child: const Center(child: CircularProgressIndicator()),
                    ),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  String _themeTitle(AppThemeMode mode, AppLocalizations l10n) {
    switch (mode) {
      case AppThemeMode.light:
        return l10n.light;
      case AppThemeMode.dark:
        return l10n.dark;
      case AppThemeMode.system:
        return l10n.system;
    }
  }

  Future<AppThemeMode?> _showThemeSheet(BuildContext context, AppLocalizations l10n, AppThemeMode current) {
    return showModalBottomSheet<AppThemeMode>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        Widget item(AppThemeMode mode, String title) {
          final selected = mode == current;
          return ListTile(
            title: Text(title),
            trailing: selected ? const Icon(Icons.check) : null,
            onTap: () => Navigator.pop(ctx, mode),
          );
        }

        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              item(AppThemeMode.system, l10n.system),
              item(AppThemeMode.light, l10n.light),
              item(AppThemeMode.dark, l10n.dark),
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );
  }

  Future<String?> _showLanguageSheet(
      BuildContext context,
      AppLocalizations l10n,
      String current,
      ) {
    return showModalBottomSheet<String>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        Widget item(String code, String title) {
          final selected = code == current;
          return ListTile(
            title: Text(title),
            trailing: selected ? const Icon(Icons.check) : null,
            onTap: () => Navigator.pop(ctx, code),
          );
        }

        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              item('ru', 'Русский'),
              item('en', 'English'),
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );
  }


  void _showExportBottomSheet(BuildContext context, AppLocalizations l10n) {
    showModalBottomSheet<ExportFormat>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Text(l10n.export, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            ),
            ListTile(
              leading: const Icon(Icons.picture_as_pdf_outlined),
              title: Text(l10n.exportPDF),
              onTap: () => Navigator.pop(ctx, ExportFormat.pdf),
            ),
            ListTile(
              leading: const Icon(Icons.description_outlined),
              title: Text(l10n.exportCSV),
              onTap: () => Navigator.pop(ctx, ExportFormat.csv),
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    ).then((format) async {
      if (format == null || !context.mounted) return;

      final days = await _showExportPeriodSheet(context, l10n);
      if (!context.mounted) return;

      // NOTE: Export period is provided as `days`:
      // 3 / 7 / 30 / 90, or null for the whole period.
      // Keep cubit/service API intact: export period goes as the 2nd positional argument.
      context.read<SettingsCubit>().exportData(format, days: days);
    });
  }

  Future<int?> _showExportPeriodSheet(BuildContext context, AppLocalizations l10n) {
    return showModalBottomSheet<int?>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) {
        Widget item(String title, int? days) {
          return ListTile(
            title: Text(title),
            onTap: () => Navigator.pop(ctx, days),
          );
        }

        return SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Padding(
                padding: const EdgeInsets.all(16.0),
                child: Text(_tr(context, 'Период', 'Period'),
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
              ),
              item(_tr(context, '3 дня', '3 days'), 3),
              item(_tr(context, '7 дней', '7 days'), 7),
              item(_tr(context, '30 дней', '30 days'), 30),
              item(_tr(context, '90 дней', '90 days'), 90),
              item(_tr(context, 'Весь период', 'Whole period'), null),
              const SizedBox(height: 8),
            ],
          ),
        );
      },
    );
  }

  void _showClearDataDialog(BuildContext context, AppLocalizations l10n) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.clearData),
        content: Text(l10n.clearDataConfirm),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: Text(l10n.no)),
          TextButton(
            onPressed: () {
              context.read<SettingsCubit>().clearAllData();
              Navigator.pop(ctx);
            },
            child: Text(l10n.yes),
          ),
        ],
      ),
    );
  }
}

class _FigmaSwitch extends StatelessWidget {
  final bool value;
  final ValueChanged<bool> onChanged;

  final Color trackOn;
  final Color trackOff;
  final Color knobOn;
  final Color knobOff;

  final AppSpacing space;

  const _FigmaSwitch({
    required this.value,
    required this.onChanged,
    required this.trackOn,
    required this.trackOff,
    required this.knobOn,
    required this.knobOff,
    required this.space,
  });

  @override
  Widget build(BuildContext context) {
    final trackW = dp(context, space.s40);
    final trackH = dp(context, space.s24);
    final knob = dp(context, space.s20);
    final pad = dp(context, space.s2);

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => onChanged(!value),
      child: Container(
        width: trackW,
        height: trackH,
        decoration: BoxDecoration(
          color: value ? trackOn : trackOff,
          borderRadius: BorderRadius.circular(trackH / 2),
        ),
        padding: EdgeInsets.all(pad),
        child: Align(
          alignment: value ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            width: knob,
            height: knob,
            decoration: BoxDecoration(
              color: value ? knobOn : knobOff,
              shape: BoxShape.circle,
            ),
          ),
        ),
      ),
    );
  }
}
