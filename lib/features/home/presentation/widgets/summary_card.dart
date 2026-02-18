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
import 'package:blood_pressure_diary/core/utils/l10n_extensions.dart';

class SummaryCard extends StatelessWidget {
  final BloodPressureRecord? record;

  const SummaryCard({super.key, this.record});

  String _time(BuildContext context, DateTime t) {
    final locale = Localizations.localeOf(context).toLanguageTag();
    return DateFormat.Hm(locale).format(t); // locale-aware (12/24h where applicable)
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final profileState = context.watch<ProfileCubit>().state;
    int targetSys = 120;
    int targetDia = 80;
    if (profileState is ProfileLoaded) {
      targetSys = profileState.profile.targetSystolic;
      targetDia = profileState.profile.targetDiastolic;
    }

    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final shadow = context.appShadow;
    final text = context.appText;

    final width = MediaQuery.sizeOf(context).width - context.horizontalPadding * 2;
    final height = dp(context, space.s114); // фикс по макету
    final r = dp(context, radii.r10);

    final bg = isDark ? AppPalette.dark900 : AppPalette.blue600;
    final mainText = isDark ? AppPalette.dark400 : colors.textOnBrand;
    final dotColor = record == null
        ? (isDark ? AppPalette.dark600 : AppPalette.blue500)
        : BloodPressureColorUtils.getIndicatorColor(
            context,
            systolic: record!.systolic,
            diastolic: record!.diastolic,
            targetSystolic: targetSys,
            targetDiastolic: targetDia,
          );

    final dotBase = dp(context, space.s10 + space.s4 + space.s1); // 15
    final dotSize = dotBase * 1.5;

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
        dp(context, space.s6) * 1.5,
        dp(context, space.s16),
        dp(context, space.s6) * 1.5,
      ),
      child: (record == null)
          ? Center(
        child: Text(
          l10n.noData,
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
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          // 1) Давление
          Text(
            '${record!.systolic}/${record!.diastolic}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: pressureStyle,
          ),

          // 2) Пульс + галочка
          Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Row(
                  children: [
                    Text('${record!.pulse}', style: pulseStyle),
                    SizedBox(width: dp(context, space.s6)),
                    Text(l10n.bpm, style: pulseStyle),
                  ],
                ),
              ),
              SizedBox(
                width: dotSize,
                height: dotSize,
                child: Center(
                  child: Container(
                    width: dotSize,
                    height: dotSize,
                    decoration: BoxDecoration(
                      color: dotColor,
                      shape: BoxShape.circle,
                    ),
                  ),
                ),
              ),
            ],
          ),

          Row(
            children: [
              SvgPicture.asset(
                'assets/clock.svg',
                width: dp(context, space.s20),
                height: dp(context, space.s20),
                colorFilter: ColorFilter.mode(clockColor, BlendMode.srcIn),
              ),
              SizedBox(width: dp(context, space.s6)),
              Text(_time(context, record!.dateTime), style: timeStyle),
            ],
          ),
        ],
      ),
    );
  }
}
