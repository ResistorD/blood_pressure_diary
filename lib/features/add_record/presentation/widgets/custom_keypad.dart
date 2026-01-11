import 'package:flutter/material.dart';

class CustomKeypad extends StatelessWidget {
  final Function(String) onKeyPressed;
  final VoidCallback onDeletePressed;
  final List<String>? enabledKeys;

  final double horizontalPadding;
  final double gap;
  final double cellHeight;
  final double radius;

  final Color background;
  final Color deleteBackground;
  final Color foreground;
  final TextStyle textStyle;

  final double deleteIconSize;
  final Color deleteIconColor;

  const CustomKeypad({
    super.key,
    required this.onKeyPressed,
    required this.onDeletePressed,
    this.enabledKeys,
    required this.horizontalPadding,
    required this.gap,
    required this.cellHeight,
    required this.radius,
    required this.background,
    required this.deleteBackground,
    required this.foreground,
    required this.textStyle,
    required this.deleteIconSize,
    required this.deleteIconColor,
  });

  @override
  Widget build(BuildContext context) {
    const keys = <String>[
      '1','2','3',
      '4','5','6',
      '7','8','9',
      '',
      '0',
      'delete',
    ];

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: 3,
        mainAxisExtent: cellHeight,
        mainAxisSpacing: gap,
        crossAxisSpacing: gap,
      ),
      itemCount: keys.length,
      itemBuilder: (context, index) {
        final key = keys[index];
        if (key.isEmpty) return const SizedBox.shrink();

        final isDelete = key == 'delete';
        final isEnabled = isDelete || enabledKeys == null || enabledKeys!.contains(key);

        return Opacity(
          opacity: isEnabled ? 1.0 : 0.3,
          child: ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: isDelete ? deleteBackground : background,
              foregroundColor: foreground,
              elevation: 0,
              padding: EdgeInsets.zero, // ✅ чтобы иконка не “висела”
              minimumSize: const Size(double.infinity, double.infinity), // ✅ заполнить ячейку
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(radius)),
            ),
            onPressed: isEnabled ? () => isDelete ? onDeletePressed() : onKeyPressed(key) : null,
            child: Center(
              child: isDelete
                  ? Icon(
                Icons.backspace_outlined,
                size: deleteIconSize,
                color: deleteIconColor,
              )
                  : Text(key, style: textStyle),
            ),
          ),
        );
      },
    );
  }
}
