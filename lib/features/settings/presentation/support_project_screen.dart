import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/core/theme/scale.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';

class SupportProjectScreen extends StatelessWidget {
  const SupportProjectScreen({super.key});

  static const _supportEmail = 'resistor.rs@gmail.com';

  static void _snack(BuildContext context, String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _openEmail(
      BuildContext context, {
        required String subject,
        required String body,
      }) async {
    final l10n = AppLocalizations.of(context)!;

    final s = Uri.encodeComponent(subject);
    final b = Uri.encodeComponent(body);

    final uri = Uri.parse('mailto:$_supportEmail?subject=$s&body=$b');

    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) _snack(context, l10n.emailClientNotFound);
  }

  Future<void> _donate(BuildContext context, int eur, String label) async {
    final l10n = AppLocalizations.of(context)!;

    // Отличаемся от "Написать нам": другой смысл, другая рыба, сумма.
    final subject = 'Pressure Diary — ${l10n.supportProject}: €$eur ($label)';
    final body = [
      'Здравствуйте!',
      '',
      'Хочу поддержать проект: €$eur ($label).',
      '',
      'Можете подсказать самый удобный способ?',
      '',
      '—',
      'Sent from Pressure Diary',
    ].join('\n');

    await _openEmail(context, subject: subject, body: body);
  }

  Future<void> _shareApp(BuildContext context) async {
    final l10n = AppLocalizations.of(context)!;

    try {
      final info = await PackageInfo.fromPlatform();
      final packageName = info.packageName;

      // Если приложение ещё не опубликовано — ссылка просто будет "в будущее", но код рабочий.
      final playUrl = 'https://play.google.com/store/apps/details?id=$packageName';

      final text = [
        '${l10n.appTitle}',
        '',
        l10n.shareAppText,
        playUrl,
      ].join('\n');

      await Share.share(text);
    } catch (_) {
      if (context.mounted) _snack(context, l10n.actionFailed);
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;

    final colors = context.appColors;
    final space = context.appSpace;
    final txt = context.appText;

    final isDark = Theme.of(context).brightness == Brightness.dark;

    final side = dp(context, space.s20);
    final topInset = MediaQuery.paddingOf(context).top;
    final bottomInset = MediaQuery.paddingOf(context).bottom;

    final headerH = dp(context, space.s128);
    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;

    final gap20 = dp(context, space.s20);
    final gap16 = dp(context, space.s16);
    final gap12 = dp(context, space.s12);
    final gap10 = dp(context, space.s10);

    final titleStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs24),
      fontWeight: txt.w700,
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
              top: topInset + gap12,
              bottom: gap12,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SizedBox(height: gap10),
                Row(
                  children: [
                    _HeaderIconButton(
                      icon: Icons.close,
                      onTap: () => Navigator.of(context).pop(),
                    ),
                    const Spacer(),
                  ],
                ),
                SizedBox(height: gap12),
                Text(
                  l10n.supportProject,
                  style: titleStyle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
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
                          icon: Icons.local_cafe_outlined,
                          title: l10n.supportCoffee,
                          subtitle: l10n.supportCoffeeHint,
                          onTap: () => _donate(context, 2, 'coffee'),
                        ),
                        SizedBox(height: dp(context, space.s8)),
                        actionRow(
                          icon: Icons.local_pizza_outlined,
                          title: l10n.supportPizza,
                          subtitle: l10n.supportPizzaHint,
                          onTap: () => _donate(context, 3, 'pizza'),
                        ),
                        SizedBox(height: dp(context, space.s8)),
                        actionRow(
                          icon: Icons.lunch_dining_outlined,
                          title: l10n.supportBurger,
                          subtitle: l10n.supportBurgerHint,
                          onTap: () => _donate(context, 5, 'burger'),
                        ),
                        SizedBox(height: dp(context, space.s8)),
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
