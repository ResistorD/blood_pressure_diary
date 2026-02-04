import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/theme/scale.dart';
import '../../../../core/utils/blood_pressure_color_utils.dart';
import '../../../profile/presentation/bloc/profile_cubit.dart';
import '../../../profile/presentation/bloc/profile_state.dart';
import '../../data/blood_pressure_model.dart';

class RecordListItem extends StatelessWidget {
  static const Map<String, String> _tagIconByLabel = {
    'После кофе': 'assets/icons/tags/coffee.svg',
    'После еды': 'assets/icons/tags/hamburger.svg',
    'После прогулки': 'assets/icons/tags/walk.svg',
    'После нагрузки/тренировки': 'assets/icons/tags/training.svg',
    'Стресс': 'assets/icons/tags/stress.svg',
    'Плохой сон': 'assets/icons/tags/sleep.svg',
    'Принял лекарство': 'assets/icons/tags/meds.svg',
    'Пропустил приём': 'assets/icons/tags/missed_meds.svg',
    'Алкоголь': 'assets/icons/tags/alcohol.svg',
    'Головная боль': 'assets/icons/tags/headache.svg',
  };

  final BloodPressureRecord record;
  final VoidCallback? onTap;

  const RecordListItem({
    super.key,
    required this.record,
    this.onTap,
  });

  String _hhmm(DateTime t) => DateFormat('HH:mm').format(t);

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final profileState = context.watch<ProfileCubit>().state;
    int targetSys = 120;
    int targetDia = 80;
    if (profileState is ProfileLoaded) {
      targetSys = profileState.profile.targetSystolic;
      targetDia = profileState.profile.targetDiastolic;
    }

    final c = context.appColors;
    final s = context.appSpace;
    final r = context.appRadii;
    final sh = context.appShadow;
    final tx = context.appText;

    final timeW = dp(context, s.s56);
    final dotD = dp(context, s.s10 + s.s4 + s.s1); // 15
    final timeGap = dp(context, s.s8);
    final dotGap = dp(context, s.s12);

    final iconSize = dp(context, s.s22);
    final iconGap = dp(context, s.s6);
    final blockGap = dp(context, s.s8);

    final cardR = dp(context, r.r5);
    final padH = dp(context, s.s20);

    final note = (record.note ?? '').trim();
    final hasNote = note.isNotEmpty;

    final tags = record.tags;
    final hasTags = tags.isNotEmpty;

    final hasMeta = hasNote || hasTags;

    final rowH = dp(context, hasMeta ? s.s72 : s.s56);
    final padV = dp(context, hasMeta ? s.s8 : s.s10);

    final valueStyle = TextStyle(
      fontFamily: tx.family,
      fontSize: sp(context, tx.fs22),
      fontWeight: tx.w700,
      color: c.textPrimary,
      height: 1.0,
    );

    final timeStyle = TextStyle(
      fontFamily: tx.family,
      fontSize: sp(context, tx.fs16),
      fontWeight: tx.w400,
      color: c.textPrimary,
      height: 1.0,
    );

    final noteStyle = TextStyle(
      fontFamily: tx.family,
      fontSize: sp(context, tx.fs14),
      fontWeight: tx.w400,
      color: c.textSecondary,
      height: 1.0,
    );

    final cardBg = isDark ? AppPalette.dark700 : c.surface;
    final iconColor = c.iconPrimary.withValues(alpha: 0.75);

    final leftTopPad = dp(context, hasMeta ? s.s12 : s.s18);
    final dotTopPad = dp(context, hasMeta ? s.s12 : s.s20);

    final dotColor = BloodPressureColorUtils.getIndicatorColor(
      context,
      systolic: record.systolic,
      diastolic: record.diastolic,
      targetSystolic: targetSys,
      targetDiastolic: targetDia,
    );

    return SizedBox(
      height: rowH,
      child: InkWell(
        onTap: onTap,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(
              width: timeW,
              child: Padding(
                padding: EdgeInsets.only(top: leftTopPad),
                child: Text(_hhmm(record.dateTime), style: timeStyle),
              ),
            ),
            SizedBox(width: timeGap),
            Padding(
              padding: EdgeInsets.only(top: dotTopPad),
              child: Container(
                width: dotD,
                height: dotD,
                decoration: BoxDecoration(color: dotColor, shape: BoxShape.circle),
              ),
            ),
            SizedBox(width: dotGap),
            Expanded(
              child: Container(
                height: rowH,
                padding: EdgeInsets.symmetric(horizontal: padH, vertical: padV),
                decoration: BoxDecoration(
                  color: cardBg,
                  borderRadius: BorderRadius.circular(cardR),
                  boxShadow: [sh.card],
                ),
                child: hasMeta
                    ? Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _MainRow(
                        record: record,
                        valueStyle: valueStyle,
                        iconSize: iconSize,
                        iconGap: iconGap,
                        blockGap: blockGap,
                        iconColor: iconColor,
                      ),
                      SizedBox(height: dp(context, s.s8)),
                      _TagsMetaRow(
                        tags: tags,
                        note: note,
                        noteStyle: noteStyle,
                        iconColor: iconColor,
                        iconSize: dp(context, s.s14),
                        gap: dp(context, s.s6),
                      ),
                    ],
                  ),
                )
                    : Center(
                  child: _MainRow(
                    record: record,
                    valueStyle: valueStyle,
                    iconSize: iconSize,
                    iconGap: iconGap,
                    blockGap: blockGap,
                    iconColor: iconColor,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}


class _TagsMetaRow extends StatelessWidget {
  final List<String> tags;
  final String note;
  final TextStyle noteStyle;
  final Color iconColor;
  final double iconSize;
  final double gap;

  const _TagsMetaRow({
    required this.tags,
    required this.note,
    required this.noteStyle,
    required this.iconColor,
    required this.iconSize,
    required this.gap,
  });

  @override
  Widget build(BuildContext context) {
    final icons = <String>[];
    for (final t in tags) {
      final p = RecordListItem._tagIconByLabel[t];
      if (p != null) icons.add(p);
    }

    final showText = note.trim().isNotEmpty || tags.isEmpty;
    final text = note.trim().isNotEmpty ? note.trim() : tags.join(', ');

    return Row(
      children: [
        if (icons.isNotEmpty)
          Flexible(
            flex: 0,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final p in icons.take(4)) ...[
                  SvgPicture.asset(
                    p,
                    width: iconSize,
                    height: iconSize,
                  ),
                  SizedBox(width: gap),
                ],
              ],
            ),
          ),
        if (icons.isNotEmpty && showText) SizedBox(width: gap),
        if (showText)
          Expanded(
            child: Text(
              text,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: noteStyle,
            ),
          ),
      ],
    );
  }
}

class _MainRow extends StatelessWidget {
  final BloodPressureRecord record;
  final TextStyle valueStyle;
  final double iconSize;
  final double iconGap;
  final double blockGap;
  final Color iconColor;

  const _MainRow({
    required this.record,
    required this.valueStyle,
    required this.iconSize,
    required this.iconGap,
    required this.blockGap,
    required this.iconColor,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: Text(
                '${record.systolic}/${record.diastolic}',
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: valueStyle,
              ),
            ),
            SizedBox(width: iconGap),
            SvgPicture.asset(
              'assets/arrow-up-down.svg',
              width: iconSize,
              height: iconSize,
              colorFilter: ColorFilter.mode(iconColor, BlendMode.srcIn),
            ),
          ],
        ),
        SizedBox(width: blockGap),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('${record.pulse}', maxLines: 1, overflow: TextOverflow.ellipsis, style: valueStyle),
            SizedBox(width: iconGap),
            SvgPicture.asset(
              'assets/activity.svg',
              width: iconSize,
              height: iconSize,
              colorFilter: ColorFilter.mode(iconColor, BlendMode.srcIn),
            ),
          ],
        ),
      ],
    );
  }
}