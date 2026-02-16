import 'package:flutter/material.dart';

/// ✅ Helper для отображения loading индикатора во время долгих операций
class LoadingOverlay {
  static void show(BuildContext context, {String? message}) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => PopScope(
        canPop: false,
        child: Center(
          child: Card(
            child: Padding(
              padding: const EdgeInsets.all(24.0),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const CircularProgressIndicator(),
                  if (message != null) ...[
                    const SizedBox(height: 16),
                    Text(
                      message,
                      style: const TextStyle(fontSize: 16),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  static void hide(BuildContext context) {
    Navigator.of(context, rootNavigator: true).pop();
  }

  /// Выполнить асинхронную операцию с автоматическим показом/скрытием loading
  static Future<T> wrapAsync<T>(
    BuildContext context,
    Future<T> Function() operation, {
    String? message,
  }) async {
    show(context, message: message);
    try {
      final result = await operation();
      if (context.mounted) hide(context);
      return result;
    } catch (e) {
      if (context.mounted) hide(context);
      rethrow;
    }
  }
}
