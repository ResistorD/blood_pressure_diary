import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:flutter/services.dart';
import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/core/theme/scale.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';

class SupportProjectScreen extends StatelessWidget {
  const SupportProjectScreen({super.key});

  static const _kofi = 'https://ko-fi.com/pressurediary';
  static const _sbpPhone = '+7 927 105 09 99';

  static void _snack(BuildContext context, String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _shareApp(BuildContext context) async {
    final l10n = AppLocalizations.of(context);

    try {
      const appUrl = 'https://resistord.github.io/pressure-diary-site';

      final text = [l10n.appTitle, '', l10n.shareAppText, appUrl].join('\n');

      await Share.share(text);
    } catch (_) {
      if (context.mounted) _snack(context, l10n.actionFailed);
    }
  }

  Future<void> _openKofi(BuildContext context) async {
    try {
      final ok = await launchUrl(
        Uri.parse(_kofi),
        mode: LaunchMode.externalApplication,
      );
      if (!ok && context.mounted) {
        _snack(context, AppLocalizations.of(context).actionFailed);
      }
    } catch (_) {
      if (context.mounted) {
        _snack(context, AppLocalizations.of(context).actionFailed);
      }
    }
  }

  Future<void> _copyPhone(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: _sbpPhone));
    if (context.mounted) {
      final ru = Localizations.localeOf(context).languageCode == 'ru';
      _snack(context, ru ? 'Номер скопирован' : 'Phone copied');
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);

    final colors = context.appColors;
    final space = context.appSpace;
    final txt = context.appText;

    final isDark = Theme.of(context).brightness == Brightness.dark;

    final side = context.horizontalPadding;
    final topInset = MediaQuery.paddingOf(context).top;
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    final headerH = dp(context, space.s128);
    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;

    final gap20 = dp(context, space.s20);
    final gap16 = dp(context, space.s16);

    final titleStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs24),
      fontWeight: txt.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final bodyStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs14),
      fontWeight: txt.w400,
      color: colors.textPrimary,
      height: 1.45,
    );

    final cardR = dp(context, context.appRadii.r10);
    final cardBg = colors.surface;
    final innerBg = isDark ? colors.surfaceAlt : AppPalette.grey050;

    Widget actionRow({
      required IconData icon,
      required String title,
      String? subtitle,
      required VoidCallback onTap,
    }) {
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: innerBg,
            borderRadius: BorderRadius.circular(cardR),
          ),
          padding: EdgeInsets.symmetric(
            horizontal: dp(context, space.s12),
            vertical: dp(context, space.s12),
          ),
          child: Row(
            children: [
              Icon(icon, color: colors.textPrimary),
              SizedBox(width: dp(context, space.s12)),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: TextStyle(
                        fontFamily: txt.family,
                        fontSize: sp(context, txt.fs16),
                        fontWeight: txt.w600,
                        color: colors.textPrimary,
                        height: 1.0,
                      ),
                    ),
                    if (subtitle != null && subtitle.trim().isNotEmpty) ...[
                      SizedBox(height: dp(context, space.s4)),
                      Text(subtitle, style: bodyStyle),
                    ],
                  ],
                ),
              ),
              Icon(Icons.chevron_right, color: colors.textPrimary),
            ],
          ),
        ),
      );
    }

    // Чтоб “(1)” не мозолил глаза в релизе.
    Widget versionLine() {
      return FutureBuilder<PackageInfo>(
        future: PackageInfo.fromPlatform(),
        builder: (context, snap) {
          final v = snap.data?.version ?? '—';
          final b = snap.data?.buildNumber ?? '—';

          final text = kReleaseMode ? v : '$v ($b)';

          return Text(
            '${l10n.version}: $text',
            style: TextStyle(
              fontFamily: txt.family,
              fontSize: sp(context, txt.fs12),
              fontWeight: txt.w400,
              color: isDark ? AppPalette.dark350 : AppPalette.grey500,
              height: 1.0,
            ),
          );
        },
      );
    }

    return Scaffold(
      backgroundColor: colors.background,
      body: Column(
        children: [
          // Header
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
                Text(
                  l10n.supportProject,
                  style: titleStyle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
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

          // Content
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
                  Container(
                    width: double.infinity,
                    decoration: BoxDecoration(
                      color: cardBg,
                      borderRadius: BorderRadius.circular(cardR),
                      boxShadow: [context.appShadow.card],
                    ),
                    padding: EdgeInsets.all(dp(context, space.s12)),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(l10n.supportProjectText, style: bodyStyle),
                        SizedBox(height: gap16),
                        versionLine(),
                      ],
                    ),
                  ),

                  SizedBox(height: gap16),

                  Container(
                    width: double.infinity,
                    decoration: BoxDecoration(
                      color: cardBg,
                      borderRadius: BorderRadius.circular(cardR),
                      boxShadow: [context.appShadow.card],
                    ),
                    padding: EdgeInsets.all(dp(context, space.s12)),
                    child: Column(
                      children: [
                        actionRow(
                          icon: Icons.public,
                          title: 'Ko-fi',
                          subtitle:
                              Localizations.localeOf(context).languageCode ==
                                  'ru'
                              ? 'Угостить кофе ☕'
                              : 'Buy Pressure Diary a coffee ☕',
                          onTap: () => _openKofi(context),
                        ),
                        SizedBox(height: dp(context, space.s8)),
                        if (Localizations.localeOf(context).languageCode ==
                            'ru') ...[
                          actionRow(
                            icon: Icons.payments_outlined,
                            title: 'Поддержать через СБП',
                            subtitle: 'Скопировать номер телефона',
                            onTap: () => _copyPhone(context),
                          ),
                          SizedBox(height: dp(context, space.s8)),
                        ],
                        actionRow(
                          icon: Icons.ios_share_outlined,
                          title: l10n.shareApp,
                          subtitle: l10n.shareAppHint,
                          onTap: () => _shareApp(context),
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
