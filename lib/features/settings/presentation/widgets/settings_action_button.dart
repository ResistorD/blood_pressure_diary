import 'package:flutter/material.dart';

import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/core/theme/scale.dart';

class SettingsActionButton extends StatelessWidget {
  final String title;
  final VoidCallback onTap;
  final double width;
  final double height;
  final Color backgroundColor;
  final double borderRadius;
  final BoxShadow shadow;
  final TextStyle textStyle;
  final AppSpacing space;

  const SettingsActionButton({
    super.key,
    required this.title,
    required this.onTap,
    required this.width,
    required this.height,
    required this.backgroundColor,
    required this.borderRadius,
    required this.shadow,
    required this.textStyle,
    required this.space,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: SizedBox(
        width: width,
        height: height,
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(borderRadius),
            boxShadow: [shadow],
          ),
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: dp(context, space.s16)),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(title, style: textStyle),
            ),
          ),
        ),
      ),
    );
  }
}
