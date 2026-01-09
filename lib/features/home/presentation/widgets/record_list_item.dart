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

  @override
  Widget build(BuildContext context) {
    final rowH = dp(context, 59);
    final timeW = dp(context, 56);
    final dotD = dp(context, 15);

    final pillR = dp(context, 6);
    final padH = dp(context, 20);
    final padV = dp(context, 10);

    final iconSize = dp(context, 22);
    final iconGap = dp(context, 8);

    final valueStyle = TextStyle(
      fontFamily: 'Inter',
      fontSize: sp(context, 22),
      fontWeight: FontWeight.w700,
      color: AppUI.textPrimary,
      height: 1.0,
    );

    final timeStyle = TextStyle(
      fontFamily: 'Inter',
      fontSize: sp(context, 16),
      fontWeight: FontWeight.w400,
      color: AppUI.textTime,
      height: 1.0,
    );

    final dotColor = record.statusColor;

    return SizedBox(
      height: rowH,
      child: InkWell(
        onTap: onTap,
        child: Row(
          children: [
            SizedBox(
              width: timeW,
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(_hhmm(record.dateTime), style: timeStyle),
              ),
            ),
            SizedBox(width: dp(context, 8)),
            Container(
              width: dotD,
              height: dotD,
              decoration: BoxDecoration(
                color: dotColor,
                shape: BoxShape.circle,
              ),
            ),
            SizedBox(width: dp(context, 12)),
            Expanded(
              child: Container(
                height: rowH,
                padding: EdgeInsets.symmetric(horizontal: padH, vertical: padV),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(pillR),
                  boxShadow: const [
                    BoxShadow(
                      offset: Offset(0, 2),
                      blurRadius: 4,
                      color: Color(0x1A000000),
                    )
                  ],
                ),
                child: Row(
                  children: [
                    // ЛЕВАЯ ГРУППА: давление + стрелки (иконка рядом с давлением)
                    Expanded(
                      flex: 3,
                      child: Row(
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
                            colorFilter: ColorFilter.mode(
                              AppUI.textPrimary.withValues(alpha: 0.75),
                              BlendMode.srcIn,
                            ),
                          ),
                        ],
                      ),
                    ),

                    // ПРАВАЯ ГРУППА: пульс + activity (прижато вправо)
                    Expanded(
                      flex: 2,
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.end,
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
                            colorFilter: ColorFilter.mode(
                              AppUI.textPrimary.withValues(alpha: 0.75),
                              BlendMode.srcIn,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
