import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/scale.dart';
import '../../data/blood_pressure_model.dart';

class SummaryCard extends StatelessWidget {
  final BloodPressureRecord? record;
  final double? width;
  final double? height;

  const SummaryCard({
    super.key,
    this.record,
    this.width,
    this.height,
  });

  String _hhmm(DateTime t) => DateFormat('HH:mm').format(t);

  @override
  Widget build(BuildContext context) {
    final cardW = width ?? (MediaQuery.sizeOf(context).width - 2 * dp(context, 20));
    final cardH = height ?? dp(context, 120);
    final r = dp(context, 10);

    const summaryBlue = Color(0xFF3973A2);

    if (record == null) {
      return Container(
        width: cardW,
        height: cardH,
        decoration: BoxDecoration(
          color: summaryBlue,
          borderRadius: BorderRadius.circular(r),
          boxShadow: const [
            BoxShadow(
              offset: Offset(0, 2),
              blurRadius: 4,
              color: Color(0x1A000000),
            ),
          ],
        ),
        alignment: Alignment.center,
        child: Text(
          'Нет данных',
          style: TextStyle(
            color: Colors.white,
            fontSize: sp(context, 18),
            fontWeight: FontWeight.w500,
            fontFamily: 'Inter',
            height: 1.0,
          ),
        ),
      );
    }

    final s = record!.systolic;
    final d = record!.diastolic;
    final p = record!.pulse;
    final t = record!.dateTime;

    final pressureStyle = TextStyle(
      fontFamily: 'Inter',
      fontSize: sp(context, 30),
      fontWeight: FontWeight.w700,
      color: Colors.white,
      height: 1.0,
    );

    final pulseNumStyle = TextStyle(
      fontFamily: 'Inter',
      fontSize: sp(context, 20),
      fontWeight: FontWeight.w600,
      color: Colors.white,
      height: 1.0,
    );

    final pulseUnitStyle = TextStyle(
      fontFamily: 'Inter',
      fontSize: sp(context, 20),
      fontWeight: FontWeight.w600,
      color: Colors.white,
      height: 1.0,
    );

    final timeStyle = TextStyle(
      fontFamily: 'Inter',
      fontSize: sp(context, 20),
      fontWeight: FontWeight.w600,
      color: Colors.white,
      height: 1.0,
    );

    return Container(
      width: cardW,
      height: cardH,
      decoration: BoxDecoration(
        color: summaryBlue,
        borderRadius: BorderRadius.circular(r),
        boxShadow: const [
          BoxShadow(
            offset: Offset(0, 2),
            blurRadius: 4,
            color: Color(0x1A000000),
          ),
        ],
      ),
      padding: EdgeInsets.fromLTRB(dp(context, 16), dp(context, 10), dp(context, 16), dp(context, 10)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 1) Давление + чек
          Row(
            children: [
              Expanded(
                child: Text(
                  '$s/$d',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: pressureStyle,
                ),
              ),
              SvgPicture.asset(
                'assets/check.svg',
                width: dp(context, 42),
                height: dp(context, 42),
                colorFilter: const ColorFilter.mode(Color(0xFF6B9DC0), BlendMode.srcIn),
              ),
            ],
          ),

          SizedBox(height: dp(context, 8)),

          // 2) Пульс: "65 уд/мин" в ОДНУ строку, без переносов
          Row(
            crossAxisAlignment: CrossAxisAlignment.baseline,
            textBaseline: TextBaseline.alphabetic,
            children: [
              Text('$p', style: pulseNumStyle),
              SizedBox(width: dp(context, 6)),
              Text('уд/мин', style: pulseUnitStyle),
            ],
          ),

          const Spacer(),

          // 3) Время
          Row(
            children: [
              SvgPicture.asset(
                'assets/clock.svg',
                width: dp(context, 20),
                height: dp(context, 20),
                colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
              ),
              SizedBox(width: dp(context, 6)),
              Text(_hhmm(t), style: timeStyle),
            ],
          ),
        ],
      ),
    );
  }
}
