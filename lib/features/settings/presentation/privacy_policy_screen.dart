import 'package:flutter/material.dart';
import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/core/theme/scale.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';

class PrivacyPolicyScreen extends StatelessWidget {
  const PrivacyPolicyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final space = context.appSpace;
    final txt = context.appText;

    final isDark = Theme.of(context).brightness == Brightness.dark;

    // фиксированный внешний горизонтальный паддинг (как на экране ввода)
    final side = context.horizontalPadding;

    final topInset = MediaQuery.paddingOf(context).top;
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    final headerH = dp(context, space.s128);

    final gap20 = dp(context, space.s20);
    final gap16 = dp(context, space.s16);

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;

    final l10n = AppLocalizations.of(context);

    const lastUpdate = '15.02.2026';

    final titleStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs24),
      fontWeight: txt.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final metaStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs12),
      fontWeight: txt.w400,
      color: isDark ? AppPalette.dark350 : AppPalette.grey500,
      height: 1.0,
    );

    final bodyStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs14),
      fontWeight: txt.w400,
      color: colors.textPrimary,
      height: 1.45,
    );

    return Scaffold(
      backgroundColor: colors.background,
      body: Column(
        children: [
          // ШАПКА — как на экране ввода: цвет, отступы, крестик
          Container(
            height: headerH,
            width: double.infinity,
            color: headerBg,
            padding: EdgeInsets.only(
              left: side,
              right: side,
              top: topInset + dp(context, space.s20),
            ),
            child: Stack(
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    l10n.privacyPolicy,
                    style: titleStyle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Align(
                  alignment: Alignment.topRight,
                  child: _HeaderIconButton(
                    icon: Icons.close,
                    onTap: () => Navigator.of(context).pop(),
                  ),
                ),
              ],
            ),
          ),

          // КОНТЕНТ
          Expanded(
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              padding: EdgeInsets.only(
                left: side,
                right: side,
                top: gap20,
                bottom: gap20 + bottomInset,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${l10n.privacyPolicyLastUpdate} $lastUpdate',
                    style: metaStyle,
                  ),
                  SizedBox(height: gap16),
                  Text(l10n.privacyPolicyFullText, style: bodyStyle),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _HeaderIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _HeaderIconButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final space = context.appSpace;

    final size = dp(context, space.s24);
    return SizedBox(
      width: size,
      height: size,
      child: IconButton(
        padding: EdgeInsets.zero,
        constraints: const BoxConstraints(),
        icon: Icon(icon, color: colors.textOnBrand, size: size),
        onPressed: onTap,
      ),
    );
  }
}
