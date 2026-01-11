import 'package:flutter/material.dart';

/// Единственный источник правды для UI:
/// - цвета (light/dark)
/// - размеры (spacing, icon sizes, базовые компоненты)
/// - радиусы
/// - тени
/// - типографика
///
/// Правило проекта: в UI-файлах — никаких хардкодов.
/// Всё берётся либо из ThemeExtension (context.appColors / appSpace / appRadii / appShadow / appText),
/// либо (временно для старого кода) из AppUI.
///
/// ВАЖНО:
/// - Тему делаем “один раз по всем JSON”.
/// - Дальше доводим экраны по очереди, НЕ возвращаясь к app_theme.dart.

@immutable
class _C {
  static const Color black = Color(0xFF000000);
  static const Color white = Color(0xFFFFFFFF);
}

// -----------------------------------------------------------------------------
// Raw palette (из всех JSON в пакете)

class AppPalette {
  // Blues
  static const Color blue900 = Color(0xFF2E5D85); // rgb(46,93,133)
  static const Color blue700 = Color(0xFF4D83AC); // rgb(77,131,172)
  static const Color blue600 = Color(0xFF3973A2); // rgb(57,115,162)
  static const Color blue500 = Color(0xFF6B9DC0); // rgb(107,157,192)
  static const Color blue300 = Color(0xFFBFD4E7); // rgb(191,212,231)

  // Greys (light)
  static const Color grey050 = Color(0xFFF9F8FA); // rgb(249,248,250)
  static const Color grey100 = Color(0xFFF5F5F5); // rgb(245,245,245)
  static const Color grey200 = Color(0xFFF0F4F8); // rgb(240,244,248)
  static const Color grey400 = Color(0xFFD9D9D9); // rgb(217,217,217)
  static const Color grey500 = Color(0xFFA0AEC0); // rgb(160,174,192)
  static const Color grey600 = Color(0xFF808080); // rgb(128,128,128)

  // Greys (dark)
  static const Color dark900 = Color(0xFF2D2D2D); // rgb(45,45,45)
  static const Color dark800 = Color(0xFF3C3C3C); // rgb(60,60,60)
  static const Color dark700 = Color(0xFF4C4C4C); // rgb(76,76,76)
  static const Color dark400 = Color(0xFFCCCCCC); // rgb(204,204,204)
  static const Color dark350 = Color(0xFFC6C6C6); // rgb(198,198,198)
  static const Color dark600 = Color(0xFF747474); // rgb(116,116,116)

  // Accents
  static const Color green = Color(0xFF3DBE65); // rgb(61,190,101)
  static const Color red = Color(0xFFDA3F3F); // rgb(218,63,63)
  static const Color blueAccent = Color(0xFF5A8EF6); // rgb(90,142,246)
  static const Color amber = Color(0xFFEB8F00); // rgb(235,143,0)

  // Error-ish variants present in some JSON
  static const Color red600 = Color(0xFFCC3333);
  static const Color redM3 = Color(0xFFF44336);
  static const Color redSoft = Color(0xFFFF8A80);
  static const Color redDark = Color(0xFFC62828);
  static const Color redWarm = Color(0xFFED7770);
  static const Color yellow = Color(0xFFFDD835);

  // Browns (встречаются в профиле)
  static const Color brown900 = Color(0xFF422B0D);
  static const Color brown700 = Color(0xFF896024);

  // Shadows
  static const Color shadow10 = Color(0x1A000000); // rgba(0,0,0,0.1)
  static const Color shadow25 = Color(0x40000000); // rgba(0,0,0,0.25)
}

// -----------------------------------------------------------------------------
// Semantic colors (то, чем реально должен пользоваться UI)

@immutable
class AppColors extends ThemeExtension<AppColors> {
  // Surfaces
  final Color background; // экран
  final Color surface; // карточки/поля
  final Color surfaceAlt; // вторичный фон/подложки

  // Brand
  final Color brand; // основной бренд (кнопки/акценты)
  final Color brandStrong; // более тёмный бренд (иконки/текст)
  final Color brandSoft; // мягкий бренд (чипы/подложки)

  // Text
  final Color textPrimary;
  final Color textSecondary;
  final Color textOnBrand;

  // Dividers
  final Color divider;

  // Icons
  final Color iconPrimary;
  final Color iconSecondary;

  // Status
  final Color success;
  final Color warning;
  final Color danger;
  final Color dangerSoft;

  // Shadow color
  final Color shadow;

  // Profile extras
  final Color profileAccentBrown;
  final Color profileAccentBrownDark;

  const AppColors({
    required this.background,
    required this.surface,
    required this.surfaceAlt,
    required this.brand,
    required this.brandStrong,
    required this.brandSoft,
    required this.textPrimary,
    required this.textSecondary,
    required this.textOnBrand,
    required this.divider,
    required this.iconPrimary,
    required this.iconSecondary,
    required this.success,
    required this.warning,
    required this.danger,
    required this.dangerSoft,
    required this.shadow,
    required this.profileAccentBrown,
    required this.profileAccentBrownDark,
  });

  static const AppColors light = AppColors(
    background: AppPalette.grey200,
    surface: _C.white,
    surfaceAlt: AppPalette.grey050,
    brand: AppPalette.blue600,
    brandStrong: AppPalette.blue900,
    brandSoft: AppPalette.blue500,
    textPrimary: AppPalette.blue900,
    textSecondary: AppPalette.grey500,
    textOnBrand: _C.white,
    divider: AppPalette.shadow10,
    iconPrimary: AppPalette.blue900,
    iconSecondary: AppPalette.blue900,
    success: AppPalette.green,
    warning: AppPalette.amber,
    danger: AppPalette.red,
    dangerSoft: AppPalette.redSoft,
    shadow: AppPalette.shadow10,
    profileAccentBrown: AppPalette.brown700,
    profileAccentBrownDark: AppPalette.brown900,
  );

  static const AppColors dark = AppColors(
    background: AppPalette.dark900,
    surface: AppPalette.dark700,
    surfaceAlt: AppPalette.dark800,
    brand: AppPalette.dark800,
    brandStrong: AppPalette.dark400,
    brandSoft: AppPalette.dark700,
    textPrimary: AppPalette.dark400,
    textSecondary: AppPalette.dark350,
    textOnBrand: _C.white,
    divider: Colors.transparent,
    iconPrimary: AppPalette.dark400,
    iconSecondary: AppPalette.dark400,
    success: AppPalette.green,
    warning: AppPalette.amber,
    danger: AppPalette.red,
    dangerSoft: AppPalette.redWarm,
    shadow: AppPalette.shadow10,
    profileAccentBrown: AppPalette.brown700,
    profileAccentBrownDark: AppPalette.brown900,
  );

  @override
  AppColors copyWith({
    Color? background,
    Color? surface,
    Color? surfaceAlt,
    Color? brand,
    Color? brandStrong,
    Color? brandSoft,
    Color? textPrimary,
    Color? textSecondary,
    Color? textOnBrand,
    Color? divider,
    Color? iconPrimary,
    Color? iconSecondary,
    Color? success,
    Color? warning,
    Color? danger,
    Color? dangerSoft,
    Color? shadow,
    Color? profileAccentBrown,
    Color? profileAccentBrownDark,
  }) {
    return AppColors(
      background: background ?? this.background,
      surface: surface ?? this.surface,
      surfaceAlt: surfaceAlt ?? this.surfaceAlt,
      brand: brand ?? this.brand,
      brandStrong: brandStrong ?? this.brandStrong,
      brandSoft: brandSoft ?? this.brandSoft,
      textPrimary: textPrimary ?? this.textPrimary,
      textSecondary: textSecondary ?? this.textSecondary,
      textOnBrand: textOnBrand ?? this.textOnBrand,
      divider: divider ?? this.divider,
      iconPrimary: iconPrimary ?? this.iconPrimary,
      iconSecondary: iconSecondary ?? this.iconSecondary,
      success: success ?? this.success,
      warning: warning ?? this.warning,
      danger: danger ?? this.danger,
      dangerSoft: dangerSoft ?? this.dangerSoft,
      shadow: shadow ?? this.shadow,
      profileAccentBrown: profileAccentBrown ?? this.profileAccentBrown,
      profileAccentBrownDark: profileAccentBrownDark ?? this.profileAccentBrownDark,
    );
  }

  @override
  AppColors lerp(ThemeExtension<AppColors>? other, double t) {
    if (other is! AppColors) return this;
    return AppColors(
      background: Color.lerp(background, other.background, t)!,
      surface: Color.lerp(surface, other.surface, t)!,
      surfaceAlt: Color.lerp(surfaceAlt, other.surfaceAlt, t)!,
      brand: Color.lerp(brand, other.brand, t)!,
      brandStrong: Color.lerp(brandStrong, other.brandStrong, t)!,
      brandSoft: Color.lerp(brandSoft, other.brandSoft, t)!,
      textPrimary: Color.lerp(textPrimary, other.textPrimary, t)!,
      textSecondary: Color.lerp(textSecondary, other.textSecondary, t)!,
      textOnBrand: Color.lerp(textOnBrand, other.textOnBrand, t)!,
      divider: Color.lerp(divider, other.divider, t)!,
      iconPrimary: Color.lerp(iconPrimary, other.iconPrimary, t)!,
      iconSecondary: Color.lerp(iconSecondary, other.iconSecondary, t)!,
      success: Color.lerp(success, other.success, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      danger: Color.lerp(danger, other.danger, t)!,
      dangerSoft: Color.lerp(dangerSoft, other.dangerSoft, t)!,
      shadow: Color.lerp(shadow, other.shadow, t)!,
      profileAccentBrown: Color.lerp(profileAccentBrown, other.profileAccentBrown, t)!,
      profileAccentBrownDark: Color.lerp(profileAccentBrownDark, other.profileAccentBrownDark, t)!,
    );
  }
}

// -----------------------------------------------------------------------------
// Spacing / sizes (набор, который встречается в JSON)

@immutable
class AppSpacing extends ThemeExtension<AppSpacing> {
  // ✅ добавили микро-токены для пиксель-перфекта
  final double s1;
  final double s2;

  final double s4;
  final double s6;
  final double s8;
  final double s10;
  final double s12;
  final double s14;
  final double s16;
  final double s18;
  final double s20;
  final double s22;
  final double s24;
  final double s26;
  final double s30;
  final double s32;
  final double s40;
  final double s48;
  final double s56;
  final double s57;
  final double s72;
  final double s80;
  final double s96;
  final double s112;
  final double s114;
  final double s120;
  final double s128;
  final double s160;

  // common widths seen in designs
  final double w320;
  final double w243;
  final double w208;
  final double w184;
  final double w96;

  const AppSpacing({
    required this.s1,
    required this.s2,
    required this.s4,
    required this.s6,
    required this.s8,
    required this.s10,
    required this.s12,
    required this.s14,
    required this.s16,
    required this.s18,
    required this.s20,
    required this.s22,
    required this.s24,
    required this.s26,
    required this.s30,
    required this.s32,
    required this.s40,
    required this.s48,
    required this.s56,
    required this.s57,
    required this.s72,
    required this.s80,
    required this.s96,
    required this.s112,
    required this.s114,
    required this.s120,
    required this.s128,
    required this.s160,
    required this.w320,
    required this.w243,
    required this.w208,
    required this.w184,
    required this.w96,
  });

  static const base = AppSpacing(
    s1: 1,
    s2: 2,
    s4: 4,
    s6: 6,
    s8: 8,
    s10: 10,
    s12: 12,
    s14: 14,
    s16: 16,
    s18: 18,
    s20: 20,
    s22: 22,
    s24: 24,
    s26: 26,
    s30: 30,
    s32: 32,
    s40: 40,
    s48: 48,
    s56: 56,
    s57: 57,
    s72: 72,
    s80: 80,
    s96: 96,
    s112: 112,
    s114: 114,
    s120: 120,
    s128: 128,
    s160: 160,
    w320: 320,
    w243: 243,
    w208: 208,
    w184: 184,
    w96: 96,
  );

  @override
  AppSpacing copyWith({
    double? s1,
    double? s2,
    double? s4,
    double? s6,
    double? s8,
    double? s10,
    double? s12,
    double? s14,
    double? s16,
    double? s18,
    double? s20,
    double? s22,
    double? s24,
    double? s26,
    double? s30,
    double? s32,
    double? s40,
    double? s48,
    double? s56,
    double? s57,
    double? s72,
    double? s80,
    double? s96,
    double? s112,
    double? s114,
    double? s120,
    double? s128,
    double? s160,
    double? w320,
    double? w243,
    double? w208,
    double? w184,
    double? w96,
  }) {
    return AppSpacing(
      s1: s1 ?? this.s1,
      s2: s2 ?? this.s2,
      s4: s4 ?? this.s4,
      s6: s6 ?? this.s6,
      s8: s8 ?? this.s8,
      s10: s10 ?? this.s10,
      s12: s12 ?? this.s12,
      s14: s14 ?? this.s14,
      s16: s16 ?? this.s16,
      s18: s18 ?? this.s18,
      s20: s20 ?? this.s20,
      s22: s22 ?? this.s22,
      s24: s24 ?? this.s24,
      s26: s26 ?? this.s26,
      s30: s30 ?? this.s30,
      s32: s32 ?? this.s32,
      s40: s40 ?? this.s40,
      s48: s48 ?? this.s48,
      s56: s56 ?? this.s56,
      s57: s57 ?? this.s57,
      s72: s72 ?? this.s72,
      s80: s80 ?? this.s80,
      s96: s96 ?? this.s96,
      s112: s112 ?? this.s112,
      s114: s114 ?? this.s114,
      s120: s120 ?? this.s120,
      s128: s128 ?? this.s128,
      s160: s160 ?? this.s160,
      w320: w320 ?? this.w320,
      w243: w243 ?? this.w243,
      w208: w208 ?? this.w208,
      w184: w184 ?? this.w184,
      w96: w96 ?? this.w96,
    );
  }

  @override
  AppSpacing lerp(ThemeExtension<AppSpacing>? other, double t) {
    return other is AppSpacing ? other : this;
  }
}

// -----------------------------------------------------------------------------
// Radii

@immutable
class AppRadii extends ThemeExtension<AppRadii> {
  final double r5;
  final double r10;
  final double r20;
  final double r30;

  const AppRadii({
    required this.r5,
    required this.r10,
    required this.r20,
    required this.r30,
  });

  static const base = AppRadii(r5: 5, r10: 10, r20: 20, r30: 30);

  @override
  AppRadii copyWith({double? r5, double? r10, double? r20, double? r30}) {
    return AppRadii(
      r5: r5 ?? this.r5,
      r10: r10 ?? this.r10,
      r20: r20 ?? this.r20,
      r30: r30 ?? this.r30,
    );
  }

  @override
  AppRadii lerp(ThemeExtension<AppRadii>? other, double t) {
    return other is AppRadii ? other : this;
  }
}

// -----------------------------------------------------------------------------
// Shadows / effects

@immutable
class AppShadows extends ThemeExtension<AppShadows> {
  final BoxShadow card; // 0 2 4 rgba(0,0,0,0.1)
  final BoxShadow strong; // rgba(0,0,0,0.25)

  const AppShadows({
    required this.card,
    required this.strong,
  });

  static const base = AppShadows(
    card: BoxShadow(
      offset: Offset(0, 2),
      blurRadius: 4,
      color: AppPalette.shadow10,
    ),
    strong: BoxShadow(
      offset: Offset(0, 2),
      blurRadius: 4,
      color: AppPalette.shadow25,
    ),
  );

  @override
  AppShadows copyWith({BoxShadow? card, BoxShadow? strong}) {
    return AppShadows(
      card: card ?? this.card,
      strong: strong ?? this.strong,
    );
  }

  @override
  AppShadows lerp(ThemeExtension<AppShadows>? other, double t) {
    return other is AppShadows ? other : this;
  }
}

// -----------------------------------------------------------------------------
// Typography

@immutable
class AppTypography extends ThemeExtension<AppTypography> {
  final String family;

  final FontWeight w400;
  final FontWeight w500;
  final FontWeight w600;
  final FontWeight w700;

  final double fs12;
  final double fs14;
  final double fs16;
  final double fs18;
  final double fs20;
  final double fs22;
  final double fs24;
  final double fs26;
  final double fs30;

  const AppTypography({
    required this.family,
    required this.w400,
    required this.w500,
    required this.w600,
    required this.w700,
    required this.fs12,
    required this.fs14,
    required this.fs16,
    required this.fs18,
    required this.fs20,
    required this.fs22,
    required this.fs24,
    required this.fs26,
    required this.fs30,
  });

  static const base = AppTypography(
    family: 'Inter',
    w400: FontWeight.w400,
    w500: FontWeight.w500,
    w600: FontWeight.w600,
    w700: FontWeight.w700,
    fs12: 12,
    fs14: 14,
    fs16: 16,
    fs18: 18,
    fs20: 20,
    fs22: 22,
    fs24: 24,
    fs26: 26,
    fs30: 30,
  );

  @override
  AppTypography copyWith({
    String? family,
    FontWeight? w400,
    FontWeight? w500,
    FontWeight? w600,
    FontWeight? w700,
    double? fs12,
    double? fs14,
    double? fs16,
    double? fs18,
    double? fs20,
    double? fs22,
    double? fs24,
    double? fs26,
    double? fs30,
  }) {
    return AppTypography(
      family: family ?? this.family,
      w400: w400 ?? this.w400,
      w500: w500 ?? this.w500,
      w600: w600 ?? this.w600,
      w700: w700 ?? this.w700,
      fs12: fs12 ?? this.fs12,
      fs14: fs14 ?? this.fs14,
      fs16: fs16 ?? this.fs16,
      fs18: fs18 ?? this.fs18,
      fs20: fs20 ?? this.fs20,
      fs22: fs22 ?? this.fs22,
      fs24: fs24 ?? this.fs24,
      fs26: fs26 ?? this.fs26,
      fs30: fs30 ?? this.fs30,
    );
  }

  @override
  AppTypography lerp(ThemeExtension<AppTypography>? other, double t) {
    return other is AppTypography ? other : this;
  }
}

// -----------------------------------------------------------------------------
// AppTheme

class AppTheme {
  static ThemeData get lightTheme => _build(
    brightness: Brightness.light,
    colors: AppColors.light,
  );

  static ThemeData get darkTheme => _build(
    brightness: Brightness.dark,
    colors: AppColors.dark,
  );

  static ThemeData _build({
    required Brightness brightness,
    required AppColors colors,
  }) {
    final typography = AppTypography.base;
    final spacing = AppSpacing.base;
    final radii = AppRadii.base;
    final shadows = AppShadows.base;

    final isDark = brightness == Brightness.dark;

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      fontFamily: typography.family,
      scaffoldBackgroundColor: colors.background,
      extensions: <ThemeExtension<dynamic>>[
        colors,
        typography,
        spacing,
        radii,
        shadows,
      ],
      colorScheme: ColorScheme.fromSeed(
        seedColor: colors.brand,
        brightness: brightness,
        primary: colors.brand,
        surface: colors.surface,
      ),
      dividerColor: colors.divider,
      cardTheme: CardThemeData(
        elevation: 0,
        color: colors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(radii.r5),
          side: BorderSide(
            color: isDark ? Colors.transparent : colors.divider,
            width: 1,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: colors.surface,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(radii.r10),
          borderSide: BorderSide.none,
        ),
        hintStyle: TextStyle(
          fontFamily: typography.family,
          fontSize: typography.fs16,
          fontWeight: typography.w400,
          color: colors.textSecondary,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: colors.brandStrong,
          foregroundColor: colors.textOnBrand,
          disabledBackgroundColor: colors.shadow,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radii.r10),
          ),
          textStyle: TextStyle(
            fontFamily: typography.family,
            fontWeight: typography.w600,
            fontSize: typography.fs20,
            height: 1.0,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          backgroundColor: colors.surface,
          foregroundColor: colors.brandStrong,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(radii.r10),
          ),
          side: BorderSide(
            color: isDark ? Colors.transparent : colors.divider,
            width: 1,
          ),
          padding: EdgeInsets.symmetric(
            vertical: spacing.s12,
            horizontal: spacing.s14,
          ),
          textStyle: TextStyle(
            fontFamily: typography.family,
            fontSize: typography.fs16,
            fontWeight: typography.w400,
            height: 1.0,
          ),
        ),
      ),
      textTheme: TextTheme(
        titleLarge: TextStyle(
          fontFamily: typography.family,
          fontSize: typography.fs26,
          fontWeight: typography.w600,
          color: colors.textOnBrand,
          height: 1.0,
        ),
        titleMedium: TextStyle(
          fontFamily: typography.family,
          fontSize: typography.fs22,
          fontWeight: typography.w600,
          color: colors.textPrimary,
          height: 1.0,
        ),
        bodyLarge: TextStyle(
          fontFamily: typography.family,
          fontSize: typography.fs18,
          fontWeight: typography.w400,
          color: colors.textPrimary,
          height: 1.0,
        ),
        bodyMedium: TextStyle(
          fontFamily: typography.family,
          fontSize: typography.fs16,
          fontWeight: typography.w400,
          color: colors.textPrimary,
          height: 1.0,
        ),
        labelLarge: TextStyle(
          fontFamily: typography.family,
          fontSize: typography.fs14,
          fontWeight: typography.w500,
          color: colors.textSecondary,
          height: 1.0,
        ),
      ),
    );
  }
}

// -----------------------------------------------------------------------------
// Context accessors

extension AppThemeX on BuildContext {
  AppColors get appColors => Theme.of(this).extension<AppColors>() ?? AppColors.light;
  AppTypography get appText => Theme.of(this).extension<AppTypography>() ?? AppTypography.base;
  AppSpacing get appSpace => Theme.of(this).extension<AppSpacing>() ?? AppSpacing.base;
  AppRadii get appRadii => Theme.of(this).extension<AppRadii>() ?? AppRadii.base;
  AppShadows get appShadow => Theme.of(this).extension<AppShadows>() ?? AppShadows.base;
}

// -----------------------------------------------------------------------------
// Legacy API (чтобы текущий код не посыпался).

class AppUI {
  // Sizes
  static const double hPad = 20.0;
  static const double cardRadius = 5.0;
  static const double fieldRadius = 10.0;
  static const double fieldHeight = 48.0;
  static const double noteHeight = 72.0;
  static const double keypadButtonWidth = 96.0;
  static const double keypadButtonHeight = 48.0;
  static const double dateButtonWidth = 208.0;
  static const double timeButtonWidth = 96.0;
  static const double dateTextWidth = 184.0;
  static const double timeTextWidth = 57.0;
  static const double noteWidth = 320.0;

  // Colors (light-ish legacy)
  static const Color primaryBlue = AppPalette.blueAccent;
  static const Color headerBlue = AppPalette.blue700;
  static const Color buttonBlue = AppPalette.blue900;
  static const Color summaryCardColor = AppPalette.blue600;
  static const Color background = AppPalette.grey200;

  static const Color textPrimary = Color(0xFF1C1C1C);
  static const Color textSecondary = AppPalette.grey500;
  static const Color textLight = AppPalette.grey500;
  static const Color textTime = AppPalette.blue900;

  static const Color accentRed = AppPalette.red;
  static const Color accentGreen = AppPalette.green;
  static const Color accentBlue = AppPalette.blueAccent;
  static const Color accentOrange = AppPalette.amber;

  static const Color todayButtonColor = AppPalette.blue500;

  static const Color white = _C.white;
  static const Color dividerColor = AppPalette.shadow10;

  static const BoxShadow shadow4x2 = BoxShadow(
    offset: Offset(0, 2),
    blurRadius: 4,
    color: AppPalette.shadow10,
  );
}
