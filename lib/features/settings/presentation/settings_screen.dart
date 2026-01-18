import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'package:blood_pressure_diary/core/services/export_service.dart';
import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/core/theme/scale.dart';
import 'package:blood_pressure_diary/features/settings/data/models/settings_model.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_cubit.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_state.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

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

    Future<TimeOfDay?> _pickTimeInput(BuildContext context) {
      return showTimePicker(
        context: context,
        initialTime: TimeOfDay.now(),
        initialEntryMode: TimePickerEntryMode.input, // без “круглых”
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

          Future<void> pickAndAddTime() async {
            final picked = await _pickTimeInput(context);
            if (picked != null && context.mounted) {
              context.read<SettingsCubit>().addReminder(picked);
            }
          }

          Future<void> pickReplaceAt(int index) async {
            final picked = await _pickTimeInput(context);
            if (picked == null || !context.mounted) return;

            if (s.reminders.length > index) {
              await context.read<SettingsCubit>().removeReminder(index);
            }
            if (context.mounted) {
              context.read<SettingsCubit>().addReminder(picked);
            }
          }

          void removeAt(int index) {
            if (index < 0 || index >= s.reminders.length) return;
            context.read<SettingsCubit>().removeReminder(index);
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

          // Минус НЕ красный, с нормальной зоной нажатия
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

            String labelForIndex(int i) {
              if (i == 0) return 'Утро';
              if (i == 1) return 'Вечер';
              return 'Время';
            }

            double rowHeightForIndex(int i) => i == 0 ? h43 : h44;

            Widget row({
              required int index,
              required String label,
              required String value,
              required double h,
            }) {
              final removable = index >= 2;

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
                      // ВАЖНО: редактирование времени доступно всегда, независимо от enabled
                      onTap: () => pickReplaceAt(index),
                      child: timeValueBox(value: value, height: h),
                    ),
                  ],
                ),
              );
            }

            return Opacity(
              // внешний вид “актив/неактив” сохраняем, но клики не блокируем
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
                      row(index: 0, label: 'Утро', value: '08:00', h: h43),
                      SizedBox(height: betweenRows),
                      row(index: 1, label: 'Вечер', value: '20:00', h: h44),
                    ] else ...[
                      for (int i = 0; i < s.reminders.length; i++) ...[
                        row(
                          index: i,
                          label: labelForIndex(i),
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
                          // ВАЖНО: добавление доступно всегда
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
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: headerBg,
                      boxShadow: [shadows.strong],
                    ),
                  ),
                ),
                Positioned(
                  left: side,
                  top: safeTop + dp(context, space.s20),
                  child: Text(l10n.settings, style: titleStyle),
                ),
                Positioned.fill(
                  top: safeTop + headerH - dp(context, space.s20),
                  child: SingleChildScrollView(
                    padding: EdgeInsets.only(
                      left: side,
                      right: side,
                      top: gap16,
                      bottom: dp(context, space.s96),
                    ),
                    child: Column(
                      children: [
                        remindersCard(),
                        SizedBox(height: gap16),
                        themeCard(),
                        SizedBox(height: gap16),

                        actionButton(title: l10n.clearData, onTap: () => _showClearDataDialog(context, l10n)),
                        SizedBox(height: gap8),
                        actionButton(
                          title: '${l10n.export} (CSV)',
                          onTap: state.isExporting ? () {} : () => _showExportBottomSheet(context, l10n),
                        ),
                        SizedBox(height: gap8),
                        actionButton(title: l10n.contactSupport, onTap: () => context.read<SettingsCubit>().contactSupport()),
                        SizedBox(height: gap8),
                        actionButton(title: l10n.rateApp, onTap: () => context.read<SettingsCubit>().rateApp()),
                        Center(child: Text(l10n.version('1.0.0'), style: versionStyle)),
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

  void _showExportBottomSheet(BuildContext context, AppLocalizations l10n) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => SafeArea(
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
              onTap: () {
                Navigator.pop(context);
                context.read<SettingsCubit>().exportData(ExportFormat.pdf);
              },
            ),
            ListTile(
              leading: const Icon(Icons.description_outlined),
              title: Text(l10n.exportCSV),
              onTap: () {
                Navigator.pop(context);
                context.read<SettingsCubit>().exportData(ExportFormat.csv);
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
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
