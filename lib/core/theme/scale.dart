import 'package:flutter/widgets.dart';

// ════════════════════════════════════════════════════════════════════════════
// 📐 УПРОЩЕННАЯ МОДЕЛЬ МАСШТАБИРОВАНИЯ v3.0 - FINAL
// ════════════════════════════════════════════════════════════════════════════
//
// ПРОБЛЕМА:
// - ResponsivePadding давал РАЗНЫЕ отступы на разных экранах
// - Poco F3: HomeScreen 20px, Settings 60px (!)
// - Причина: использовал MediaQuery.sizeOf(context) - локальный размер
//
// РЕШЕНИЕ:
// - ФИКСИРОВАННЫЕ отступы для всех экранов (20px)
// - Масштабирование ТОЛЬКО от высоты (работает лучше всего)
// - Максимальная простота - минимум магии
//
// ════════════════════════════════════════════════════════════════════════════

// Эталонная ширина (Poco F3)
// Poco F3 (1080×2400) типичный logical width в Flutter ≈ 392.
const double _designWidth = 392.0;

/// Базовый scale от ширины экрана
double _scale(BuildContext context) {
  // ВАЖНО: Используем MediaQuery.of(context).size
  // А НЕ MediaQuery.sizeOf(context)!
  //
  // MediaQuery.of(context).size - ВСЕГДА размер экрана
  // MediaQuery.sizeOf(context) - может быть размер локального виджета!
  //
  // Дополнительно страхуемся от локальных MediaQuery (оверлеи/диалоги):
  // если MediaQuery недоступен, берём размер окна из View.
  final mq = MediaQuery.maybeOf(context);
  final view = View.of(context);
  final size = mq?.size ?? (view.physicalSize / view.devicePixelRatio);

  final width = size.width;

  // На планшетах/широких экранах глобальное масштабирование чаще вредит,
  // чем помогает (раздувает UI). Оставляем 1.0.
  if (width >= 600) {
    return 1.0;
  }

  final scale = width / _designWidth;

  // Умеренные ограничения: убираем «дрейф» на разных aspect ratio,
  // но сохраняем читаемость на очень узких/широких телефонах.
  return scale.clamp(0.92, 1.10);
}

/// 📏 Горизонтальные размеры (width, padding между элементами)
double dp(BuildContext context, double designPx) {
  return designPx * _scale(context);
}

/// 📐 Вертикальные размеры (height, margins)
double vdp(BuildContext context, double designPx) {
  final size = MediaQuery.of(context).size;
  final isLandscape = size.width > size.height;

  // В landscape сжимаем вертикальные размеры
  if (isLandscape) {
    return designPx * _scale(context) * 0.70;
  }

  return designPx * _scale(context);
}

/// 🔤 Размеры шрифтов
double sp(BuildContext context, double designSp) {
  final baseScale = _scale(context);

  // Шрифты масштабируются медленнее
  final fontScale = 1.0 + (baseScale - 1.0) * 0.5;

  return designSp * fontScale.clamp(0.95, 1.20);
}

// ════════════════════════════════════════════════════════════════════════════
// ✅ ФИКСИРОВАННЫЕ ОТСТУПЫ - КЛЮЧ К РЕШЕНИЮ!
// ════════════════════════════════════════════════════════════════════════════

/// КРИТИЧЕСКИ ВАЖНО:
/// Эти отступы ФИКСИРОВАННЫЕ для ВСЕХ экранов!
/// Они НЕ зависят от context, НЕ используют MediaQuery!
///
/// Это решает проблему разных отступов на Poco F3 и Xiaomi 15T Pro.
const double _horizontalPadding =
    20.0; // Фиксированный отступ 20px для всех экранов
const double _verticalPadding =
    16.0; // Фиксированный отступ 16px для всех экранов

/// Проверка landscape
bool isLandscape(BuildContext context) {
  final size = MediaQuery.of(context).size;
  return size.width > size.height;
}

// ════════════════════════════════════════════════════════════════════════════
// АДАПТИВНЫЕ РАЗМЕРЫ ДЛЯ КОМПОНЕНТОВ
// ════════════════════════════════════════════════════════════════════════════

/// Размеры Header (HomeScreen)
class HeaderSizes {
  static double blueHeight(BuildContext context) {
    if (isLandscape(context)) {
      return vdp(context, 100);
    }

    final height = MediaQuery.of(context).size.height;

    // Увеличиваем header только для очень высоких экранов (Xiaomi 15T Pro)
    if (height > 920) {
      return vdp(context, 190);
    }

    // Все остальные - стандартный размер
    return vdp(context, 160);
  }

  static double shelfHeight(BuildContext context) {
    if (isLandscape(context)) {
      return vdp(context, 60);
    }
    return vdp(context, 80);
  }

  static double overlap(BuildContext context) {
    final height = MediaQuery.of(context).size.height;

    // Уменьшаем overlap на высоких экранах для большего зазора
    if (height > 920) {
      return dp(context, 40);
    }

    // Стандартный overlap
    return dp(context, 50);
  }

  /// ✅ Фиксированный горизонтальный отступ
  static double horizontalPadding(BuildContext context) {
    return _horizontalPadding;
  }
}

/// Размеры полей ввода (AddRecordScreen)
class InputSizes {
  static bool shouldUseCompactLayout(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final viewInsets = MediaQuery.viewInsetsOf(context);
    final availableHeight = size.height - viewInsets.bottom;
    return availableHeight < 600;
  }

  static double buttonHeight(BuildContext context) {
    if (shouldUseCompactLayout(context)) {
      return 48.0;
    }
    return dp(context, 56);
  }

  static double inputFieldHeight(BuildContext context) {
    if (shouldUseCompactLayout(context)) {
      return 60.0;
    }
    return dp(context, 80);
  }

  static double buttonSpacing(BuildContext context) {
    if (shouldUseCompactLayout(context)) {
      return 6.0;
    }
    return dp(context, 8);
  }
}

// ════════════════════════════════════════════════════════════════════════════
// ✅ EXTENSION МЕТОДЫ ДЛЯ УДОБСТВА
// ════════════════════════════════════════════════════════════════════════════

/// Extension для быстрого доступа к отступам
extension PaddingExtension on BuildContext {
  /// Фиксированный горизонтальный отступ (20px)
  double get horizontalPadding => _horizontalPadding;

  /// Фиксированный вертикальный отступ (16px)
  double get verticalPadding => _verticalPadding;

  /// Уменьшенный вертикальный отступ для landscape (8px)
  double get verticalPaddingLandscape => 8.0;

  /// Адаптивный вертикальный отступ (учитывает landscape)
  double get adaptiveVerticalPadding {
    return isLandscape(this) ? 8.0 : _verticalPadding;
  }

  /// EdgeInsets с фиксированными отступами
  EdgeInsets get pagePadding => EdgeInsets.symmetric(
    horizontal: horizontalPadding,
    vertical: adaptiveVerticalPadding,
  );

  /// Только горизонтальные отступы
  EdgeInsets get horizontalPagePadding =>
      EdgeInsets.symmetric(horizontal: horizontalPadding);

  /// Только вертикальные отступы
  EdgeInsets get verticalPagePadding =>
      EdgeInsets.symmetric(vertical: adaptiveVerticalPadding);
}
