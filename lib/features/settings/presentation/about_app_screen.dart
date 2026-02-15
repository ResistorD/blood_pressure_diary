import 'package:flutter/material.dart';
import 'package:in_app_review/in_app_review.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:url_launcher/url_launcher.dart';
import 'support_project_screen.dart';

import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/core/theme/scale.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';

import 'privacy_policy_screen.dart';

class AboutAppScreen extends StatelessWidget {
  const AboutAppScreen({super.key});

  static const _supportEmail = 'resistor.rs@gmail.com';

  Future<void> _openEmail(BuildContext context) async {
    final l10n = AppLocalizations.of(context)!;

    final subject = Uri.encodeComponent('Pressure Diary — ${l10n.contactSupport}');
    final body = Uri.encodeComponent('${l10n.contactSupport}\n');

    final uri = Uri.parse('mailto:$_supportEmail?subject=$subject&body=$body');

    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && context.mounted) {
      _snack(context, l10n.emailClientNotFound);
    }
  }

  Future<void> _rateApp(BuildContext context) async {
    final l10n = AppLocalizations.of(context)!;

    final inAppReview = InAppReview.instance;
    try {
      if (await inAppReview.isAvailable()) {
        await inAppReview.requestReview();
      } else {
        await inAppReview.openStoreListing();
      }
    } catch (_) {
      if (context.mounted) _snack(context, l10n.actionFailed);
    }
  }

  Future<void> _supportProject(BuildContext context) async {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const SupportProjectScreen()),
    );
  }


  static void _snack(BuildContext context, String text) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(text)),
    );
  }

  @override
  Widget build(BuildContext context) {
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

    final l10n = AppLocalizations.of(context)!;

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

    return Scaffold(
      backgroundColor: colors.background,
      body: Column(
        children: [
          // ШАПКА
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
                  l10n.aboutApp,
                  style: titleStyle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
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
                  // Блок "О приложении"
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
                        Text(l10n.appAboutText, style: bodyStyle),
                        SizedBox(height: gap16),
                        FutureBuilder<PackageInfo>(
                          future: PackageInfo.fromPlatform(),
                          builder: (context, snap) {
                            final v = snap.data?.version ?? '—';
                            final b = snap.data?.buildNumber ?? '—';
                            return Text(
                              '${l10n.version}: $v ($b)',
                              style: TextStyle(
                                fontFamily: txt.family,
                                fontSize: sp(context, txt.fs12),
                                fontWeight: txt.w400,
                                color: isDark ? AppPalette.dark350 : AppPalette.grey500,
                                height: 1.0,
                              ),
                            );
                          },
                        ),
                      ],
                    ),
                  ),

                  SizedBox(height: gap16),

                  // Действия
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
                          icon: Icons.mail_outline,
                          title: l10n.contactSupport,
                          subtitle: _supportEmail,
                          onTap: () => _openEmail(context),
                        ),
                        SizedBox(height: dp(context, space.s8)),
                        actionRow(
                          icon: Icons.star_outline,
                          title: l10n.rateApp,
                          onTap: () => _rateApp(context),
                        ),
                        SizedBox(height: dp(context, space.s8)),
                        actionRow(
                          icon: Icons.privacy_tip_outlined,
                          title: l10n.privacyPolicy,
                          onTap: () {
                            Navigator.of(context).push(
                              MaterialPageRoute(builder: (_) => const PrivacyPolicyScreen()),
                            );
                          },
                        ),
                        SizedBox(height: dp(context, space.s8)),
                        actionRow(
                          icon: Icons.favorite_border,
                          title: l10n.supportProject,
                          subtitle: l10n.supportProjectHint,
                          onTap: () => _supportProject(context),
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
