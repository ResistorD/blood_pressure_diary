import 'package:flutter/material.dart';

class AppUI {
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
  
  static const Color primaryBlue = Color(0xFF3D8BFC);
  static const Color headerBlue = Color(0xFF4D83AC);
  static const Color buttonBlue = Color(0xFF2E5D85);
  static const Color summaryCardColor = Color(0xFF3973A2);
  static const Color background = Color(0xFFF0F4F8);
  
  static const Color textPrimary = Color(0xFF1C1C1C);
  static const Color textSecondary = Color(0xFF718096);
  static const Color textLight = Color(0xFFA0AEC0);
  static const Color textTime = Color(0xFF325674);
  
  static const Color accentRed = Color(0xFFDA3F3F);
  static const Color accentGreen = Color(0xFF3DBE65);
  static const Color accentBlue = Color(0xFF5A8EF6);
  static const Color accentOrange = Color(0xFFDD6B20);
  
  static const Color todayButtonColor = Color(0xFF6B9DC0);
  
  static const Color white = Color(0xFFFFFFFF);
  static const Color dividerColor = Color(0xFFE2E8F0);
  static const BoxShadow shadow4x2 = BoxShadow(
    offset: Offset(0, 2),
    blurRadius: 4,
    color: Color(0x1A000000),
  );
}

class AppTheme {
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      fontFamily: 'Inter',
      scaffoldBackgroundColor: AppUI.background,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppUI.primaryBlue,
        primary: AppUI.primaryBlue,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppUI.cardRadius),
          side: BorderSide(color: Colors.grey.withValues(alpha: 0.1)),
        ),
        color: Colors.white,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppUI.white,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppUI.fieldRadius),
          borderSide: BorderSide.none,
        ),
        hintStyle: const TextStyle(color: Color(0xFF718096)),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppUI.buttonBlue,
          foregroundColor: AppUI.white,
          disabledBackgroundColor: const Color(0x1A000000),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppUI.fieldRadius),
          ),
          textStyle: const TextStyle(
            fontWeight: FontWeight.w600,
            fontSize: 20,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          backgroundColor: AppUI.white,
          foregroundColor: AppUI.buttonBlue,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppUI.fieldRadius),
          ),
          side: BorderSide(color: Colors.grey.withValues(alpha: 0.15)),
          padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 14),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w400),
        ),
      ),
      textTheme: const TextTheme(
        titleLarge: TextStyle(fontFamily: 'Inter', fontSize: 24, fontWeight: FontWeight.w600),
        titleMedium: TextStyle(fontFamily: 'Inter', fontSize: 20, fontWeight: FontWeight.w600),
        bodyLarge: TextStyle(fontFamily: 'Inter', fontSize: 18, fontWeight: FontWeight.w400),
        bodyMedium: TextStyle(fontFamily: 'Inter', fontSize: 16, fontWeight: FontWeight.w400),
        labelLarge: TextStyle(fontFamily: 'Inter', fontSize: 14, fontWeight: FontWeight.w500),
      ),
    );
  }
}
