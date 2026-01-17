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
    final height = dp(context, space.s114); // фикс по макету
    final r = dp(context, radii.r10);

    final bg = isDark ? AppPalette.dark900 : AppPalette.blue600;
    final mainText = isDark ? AppPalette.dark400 : colors.textOnBrand;
    final checkColor = isDark ? AppPalette.dark600 : AppPalette.blue500;

    // ✅ увеличили, но без убийства высоты
    final checkSize = dp(context, space.s40);

    final pressureStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs30),
      fontWeight: text.w600,
      color: mainText,
      height: 1.0,
    );

    final pulseStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs22),
      fontWeight: text.w600,
      color: mainText,
      height: 1.0,
    );

    final timeStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs22),
      fontWeight: text.w600,
      color: mainText,
      height: 1.0,
    );

    final clockColor = isDark ? AppPalette.dark600 : colors.textOnBrand;

    return Container(
      width: width,
      height: height,
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(r),
        boxShadow: [shadow.card],
      ),
      // ✅ уменьшаем вертикальные паддинги
      padding: EdgeInsets.fromLTRB(
        dp(context, space.s16),
        dp(context, space.s6),
        dp(context, space.s16),
        dp(context, space.s6),
      ),
      child: (record == null)
          ? Center(
        child: Text(
          'Нет данных',
          style: TextStyle(
            fontFamily: text.family,
            fontSize: sp(context, text.fs16),
            fontWeight: text.w500,
            color: mainText,
            height: 1.0,
          ),
        ),
      )
          : Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1) Давление
          Text(
            '${record!.systolic}/${record!.diastolic}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: pressureStyle,
          ),

          SizedBox(height: dp(context, space.s1)),

          // 2) Пульс + галочка
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Row(
                  children: [
                    Text('${record!.pulse}', style: pulseStyle),
                    SizedBox(width: dp(context, space.s6)),
                    Text('уд/мин', style: pulseStyle),
                  ],
                ),
              ),
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

          // ✅ “опустить” время визуально, но не раздувать высоту
          Padding(
            padding: EdgeInsets.only(top: dp(context, space.s4)),
            child: Row(
              children: [
                SvgPicture.asset(
                  'assets/clock.svg',
                  width: dp(context, space.s20),
                  height: dp(context, space.s20),
                  colorFilter: ColorFilter.mode(clockColor, BlendMode.srcIn),
                ),
                SizedBox(width: dp(context, space.s6)),
                Text(_hhmm(record!.dateTime), style: timeStyle),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
