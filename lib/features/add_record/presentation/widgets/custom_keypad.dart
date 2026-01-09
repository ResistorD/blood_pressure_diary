import 'package:flutter/material.dart';

class CustomKeypad extends StatelessWidget {
  final Function(String) onKeyPressed;
  final VoidCallback onDeletePressed;
  final List<String>? enabledKeys;

  /// Метрики из экрана (такие же, как у _ValuePill)
  final double horizontalPadding;
  final double gap;
  final double cellHeight;
  final double radius;

  /// (опционально) стилизация под ваш UI
  final Color background;
  final Color deleteBackground;
  final Color foreground;
  final TextStyle textStyle;

  const CustomKeypad({
    super.key,
    required this.onKeyPressed,
    required this.onDeletePressed,
    this.enabledKeys, // <-- ДОБАВЬ ЭТУ СТРОКУ
    required this.horizontalPadding,
    required this.gap,
    required this.cellHeight,
    required this.radius,
    this.background = const Color(0xFFFFFFFF),
    this.deleteBackground = const Color(0xFFE5E7EB),
    this.foreground = const Color(0xFF2E5D85),
    this.textStyle = const TextStyle(fontSize: 24, fontWeight: FontWeight.w800, height: 1.0),
  });

  @override
  Widget build(BuildContext context) {
    final keys = <String>['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', 'delete'];

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

        // ГЛАВНАЯ ЛОГИКА ТУТ:
        // Если это кнопка удаления - она всегда активна.
        // Если цифра - проверяем, есть ли она в списке разрешенных.
        final bool isEnabled = isDelete ||
            (enabledKeys == null) ||
            enabledKeys!.contains(key);

        return Opacity(
          opacity: isEnabled ? 1.0 : 0.3, // "Гасим" кнопку визуально
          child: ElevatedButton(
            style: ElevatedButton.styleFrom(
              backgroundColor: isDelete ? deleteBackground : background,
              foregroundColor: foreground,
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(radius),
              ),
            ),
            // Если кнопка не активна, передаем null в onPressed, и Flutter сам её отключит
            onPressed: isEnabled
                ? () => isDelete ? onDeletePressed() : onKeyPressed(key)
                : null,
            child: isDelete
                ? const Icon(Icons.backspace_outlined)
                : Text(key, style: textStyle),
          ),
        );
      },
    );
  }
}
