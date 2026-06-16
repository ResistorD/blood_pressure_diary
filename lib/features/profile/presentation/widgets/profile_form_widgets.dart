import 'package:flutter/material.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/theme/scale.dart';

class ProfileSectionCard extends StatelessWidget {
  final Widget child;
  final Color backgroundColor;
  final double borderRadius;
  final BoxShadow shadow;
  final EdgeInsetsGeometry padding;

  const ProfileSectionCard({
    super.key,
    required this.child,
    required this.backgroundColor,
    required this.borderRadius,
    required this.shadow,
    required this.padding,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(borderRadius),
          boxShadow: [shadow],
        ),
        child: Padding(padding: padding, child: child),
      ),
    );
  }
}

class ProfilePrimaryButton extends StatelessWidget {
  final String title;
  final String? subtitle;
  final Color backgroundColor;
  final Color foregroundColor;
  final VoidCallback onTap;
  final double height;
  final double borderRadius;
  final AppSpacing space;
  final TextStyle titleStyle;
  final TextStyle hintStyle;

  const ProfilePrimaryButton({
    super.key,
    required this.title,
    this.subtitle,
    required this.backgroundColor,
    required this.foregroundColor,
    required this.onTap,
    required this.height,
    required this.borderRadius,
    required this.space,
    required this.titleStyle,
    required this.hintStyle,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: height,
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(borderRadius),
        ),
        alignment: Alignment.center,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(title, style: titleStyle.copyWith(color: foregroundColor)),
            if (subtitle != null && subtitle!.isNotEmpty) ...[
              SizedBox(height: dp(context, space.s2)),
              Text(
                subtitle!,
                style: hintStyle.copyWith(color: foregroundColor),
                textAlign: TextAlign.center,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class ProfileWideField extends StatelessWidget {
  final String textValue;
  final VoidCallback? onTap;
  final double height;
  final double borderRadius;
  final Color backgroundColor;
  final TextStyle valueStyle;
  final AppSpacing space;

  const ProfileWideField({
    super.key,
    required this.textValue,
    this.onTap,
    required this.height,
    required this.borderRadius,
    required this.backgroundColor,
    required this.valueStyle,
    required this.space,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: height,
        width: double.infinity,
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(borderRadius),
        ),
        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
        alignment: Alignment.centerLeft,
        child: Text(textValue, style: valueStyle),
      ),
    );
  }
}

class ProfileValueBox extends StatelessWidget {
  final String textValue;
  final VoidCallback? onTap;
  final double width;
  final double height;
  final double borderRadius;
  final Color backgroundColor;
  final TextStyle valueStyle;
  final AppSpacing space;

  const ProfileValueBox({
    super.key,
    required this.textValue,
    this.onTap,
    required this.width,
    required this.height,
    required this.borderRadius,
    required this.backgroundColor,
    required this.valueStyle,
    required this.space,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: height,
        width: width,
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(borderRadius),
        ),
        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
        alignment: Alignment.centerRight,
        child: Text(textValue, style: valueStyle),
      ),
    );
  }
}

class ProfileSegmentPill extends StatelessWidget {
  final String title;
  final bool selected;
  final VoidCallback onTap;
  final double height;
  final double borderRadius;
  final Color activeBackground;
  final Color inactiveText;
  final Color activeText;
  final TextStyle valueStyle;

  const ProfileSegmentPill({
    super.key,
    required this.title,
    required this.selected,
    required this.onTap,
    required this.height,
    required this.borderRadius,
    required this.activeBackground,
    required this.inactiveText,
    required this.activeText,
    required this.valueStyle,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          height: height,
          decoration: BoxDecoration(
            color: selected ? activeBackground : Colors.transparent,
            borderRadius: BorderRadius.circular(borderRadius),
          ),
          alignment: Alignment.center,
          child: Text(
            title,
            style: valueStyle.copyWith(
              color: selected ? activeText : inactiveText,
            ),
          ),
        ),
      ),
    );
  }
}

class ProfileSheetItem extends StatelessWidget {
  final String title;
  final VoidCallback onTap;
  final double height;
  final double borderRadius;
  final Color backgroundColor;
  final TextStyle valueStyle;
  final AppSpacing space;

  const ProfileSheetItem({
    super.key,
    required this.title,
    required this.onTap,
    required this.height,
    required this.borderRadius,
    required this.backgroundColor,
    required this.valueStyle,
    required this.space,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        height: height,
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(borderRadius),
        ),
        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
        alignment: Alignment.centerLeft,
        child: Text(title, style: valueStyle),
      ),
    );
  }
}

class ProfileTextInputSheet extends StatefulWidget {
  final String title;
  final String buttonTitle;
  final String initialValue;
  final TextInputType keyboardType;
  final ValueChanged<String> onSubmit;
  final Color sheetBackground;
  final Color fieldBackground;
  final Color buttonBackground;
  final Color buttonForeground;
  final double sheetRadius;
  final double fieldHeight;
  final double fieldRadius;
  final TextStyle titleStyle;
  final TextStyle valueStyle;
  final TextStyle buttonStyle;
  final BoxShadow shadow;
  final AppSpacing space;

  const ProfileTextInputSheet({
    super.key,
    required this.title,
    required this.buttonTitle,
    required this.initialValue,
    required this.keyboardType,
    required this.onSubmit,
    required this.sheetBackground,
    required this.fieldBackground,
    required this.buttonBackground,
    required this.buttonForeground,
    required this.sheetRadius,
    required this.fieldHeight,
    required this.fieldRadius,
    required this.titleStyle,
    required this.valueStyle,
    required this.buttonStyle,
    required this.shadow,
    required this.space,
  });

  @override
  State<ProfileTextInputSheet> createState() => _ProfileTextInputSheetState();
}

class _ProfileTextInputSheetState extends State<ProfileTextInputSheet> {
  late final TextEditingController _controller;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialValue);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.viewInsetsOf(context).bottom;

    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: dp(context, widget.space.s12),
          right: dp(context, widget.space.s12),
          bottom: dp(context, widget.space.s12) + bottomInset,
          top: dp(context, widget.space.s12),
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: widget.sheetBackground,
            borderRadius: BorderRadius.circular(widget.sheetRadius),
            boxShadow: [widget.shadow],
          ),
          child: Padding(
            padding: EdgeInsets.all(dp(context, widget.space.s12)),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(widget.title, style: widget.titleStyle),
                SizedBox(height: dp(context, widget.space.s8)),
                TextField(
                  controller: _controller,
                  keyboardType: widget.keyboardType,
                  autofocus: true,
                  style: widget.valueStyle,
                  decoration: InputDecoration(
                    filled: true,
                    fillColor: widget.fieldBackground,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(widget.fieldRadius),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
                SizedBox(height: dp(context, widget.space.s12)),
                SizedBox(
                  width: double.infinity,
                  height: widget.fieldHeight,
                  child: ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: widget.buttonBackground,
                      foregroundColor: widget.buttonForeground,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(widget.fieldRadius),
                      ),
                      elevation: 0,
                    ),
                    onPressed: () {
                      widget.onSubmit(_controller.text.trim());
                      Navigator.of(context).pop();
                    },
                    child: Text(widget.buttonTitle, style: widget.buttonStyle),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
