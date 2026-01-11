import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/theme/scale.dart';
import '../../data/blood_pressure_model.dart';

class RecordListItem extends StatelessWidget {
  final BloodPressureRecord record;
  final VoidCallback? onTap;

  const RecordListItem({
    super.key,
    required this.record,
    this.onTap,
  });

  String _hhmm(DateTime t) => DateFormat('HH:mm').format(t);

  Color _dotColor(BuildContext context) {
    final c = context.appColors;

    final sys = record.systolic;
    final dia = record.diastolic;

    final isLow = sys < 100 || dia < 60;
    final isHigh = sys >= 140 || dia >= 90;
    final isElevated = !isLow && !isHigh && (sys >= 130 || dia >= 85);

    if (isHigh) return c.danger;
    if (isElevated) return c.warning;
    if (isLow) return AppPalette.blueAccent; // #FF5A8EF6
    return c.success;
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

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

    final rowH = dp(context, hasNote ? s.s72 : s.s56);

    // вертикальные паддинги оставляем симметричными
    final padV = dp(context, hasNote ? s.s8 : s.s10);

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

    final leftTopPad = dp(context, hasNote ? s.s12 : s.s18);
    final dotTopPad = dp(context, hasNote ? s.s12 : s.s20);

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
                decoration: BoxDecoration(
                  color: _dotColor(context),
                  shape: BoxShape.circle,
                ),
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
                child: hasNote
                    ? Center(
                  // ✅ ключ: центрируем блок целиком внутри фиксированной высоты
                  child: Column(
                    mainAxisSize: MainAxisSize.min, // ✅ не растягиваться
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
                      SizedBox(height: dp(context, s.s8)), // gap между цифрами и комментом
                      Text(
                        note,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: noteStyle,
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
      children: [
        Expanded(
          child: Row(
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
        ),
        SizedBox(width: blockGap),
        Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              '${record.pulse}',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: valueStyle,
            ),
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
