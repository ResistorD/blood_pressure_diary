import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/theme/scale.dart';
import '../../data/blood_pressure_model.dart';

class SummaryCard extends StatelessWidget {
  final BloodPressureRecord? record;

  const SummaryCard({super.key, this.record});

  String _hhmm(DateTime t) => DateFormat('HH:mm').format(t);

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final shadow = context.appShadow;
    final text = context.appText;

    final width = MediaQuery.sizeOf(context).width - dp(context, space.s20) * 2;
    final height = dp(context, isDark ? space.s114 : space.s112);
    final r = dp(context, radii.r10);

    final bg = isDark ? AppPalette.dark800 : AppPalette.blue600;
    final checkColor = isDark ? colors.textOnBrand : AppPalette.blue500;

    final checkSize = dp(context, space.s48); // ✅ чуть больше (было 42)

    final pressureStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs30),
      fontWeight: text.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final pulseStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs22),
      fontWeight: text.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final timeStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs22),
      fontWeight: text.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(r),
        boxShadow: [shadow.card],
      ),
      padding: EdgeInsets.fromLTRB(
        dp(context, space.s16),
        dp(context, space.s4),
        dp(context, space.s16),
        dp(context, space.s10),
      ),
      child: (record == null)
          ? Center(
        child: Text(
          'Нет данных',
          style: TextStyle(
            fontFamily: text.family,
            fontSize: sp(context, text.fs16),
            fontWeight: text.w500,
            color: colors.textOnBrand,
            height: 1.0,
          ),
        ),
      )
          : Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Давление + галочка
          Row(
            crossAxisAlignment: CrossAxisAlignment.center, // ✅ центр по вертикали
            children: [
              Expanded(
                child: Padding(
                  // ✅ чуть подняли строку давления, чтобы не упираться в низ
                  padding: EdgeInsets.only(top: dp(context, 0)),
                  child: Text(
                    '${record!.systolic}/${record!.diastolic}',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: pressureStyle,
                  ),
                ),
              ),
              SizedBox(width: dp(context, space.s2)),
              SizedBox(
                width: checkSize,
                height: checkSize,
                child: Center(
                  child: SvgPicture.asset(
                    'assets/check.svg',
                    width: checkSize,
                    height: checkSize,
                    colorFilter: ColorFilter.mode(checkColor, BlendMode.srcIn),
                  ),
                ),
              ),
            ],
          ),

          // ✅ уменьшили зазор между давлением и пульсом
          SizedBox(height: dp(context, space.s2)),

          // Пульс
          Row(
            children: [
              Text('${record!.pulse}', style: pulseStyle),
              SizedBox(width: dp(context, space.s6)),
              Text('уд/мин', style: pulseStyle),
            ],
          ),

          // ✅ чуть больше воздуха перед временем, чтобы не "слипалось"
          SizedBox(height: dp(context, space.s4)),

          // Время
          Row(
            children: [
              SvgPicture.asset(
                'assets/clock.svg',
                width: dp(context, space.s20),
                height: dp(context, space.s20),
                colorFilter: ColorFilter.mode(colors.textOnBrand, BlendMode.srcIn),
              ),
              SizedBox(width: dp(context, space.s6)),
              Text(_hhmm(record!.dateTime), style: timeStyle),
            ],
          ),
        ],
      ),
    );
  }
}
