import 'package:flutter/cupertino.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:io' show Platform;

/// Вспомогательная функция для корректного кодирования параметров mailto.
/// Заменяет '+' на '%20', чтобы в теле письма не было плюсов вместо пробелов.
String _encodeQueryParameters(Map<String, String> params) {
  return params.entries
      .map((e) => '${Uri.encodeComponent(e.key)}=${Uri.encodeComponent(e.value)}')
      .join('&')
      .replaceAll('+', '%20');
}

Future<void> launchEmail({
  required String to,
  required String subject,
  required String body,
}) async {
  // Используем ручную сборку query вместо queryParameters
  final Uri emailLaunchUri = Uri(
    scheme: 'mailto',
    path: to,
    query: _encodeQueryParameters(<String, String>{
      'subject': subject,
      'body': body,
    }),
  );

  // mode: LaunchMode.externalApplication важен для стабильности на Android
  final ok = await launchUrl(emailLaunchUri, mode: LaunchMode.externalApplication);
  if (!ok) {
    debugPrint('Could not launch email to $to');
  }
}

Future<void> rateApp({
  required String androidPackageName,
  String? iosAppId,
}) async {
  if (Platform.isAndroid) {
    final marketUri = Uri.parse('market://details?id=$androidPackageName');
    if (await canLaunchUrl(marketUri)) {
      await launchUrl(marketUri, mode: LaunchMode.externalApplication);
      return;
    }
    final webUri = Uri.parse('https://play.google.com/store/apps/details?id=$androidPackageName');
    await launchUrl(webUri, mode: LaunchMode.externalApplication);
    return;
  }

  if (Platform.isIOS) {
    if (iosAppId != null && iosAppId.isNotEmpty) {
      final url = Uri.parse('https://apps.apple.com/app/id$iosAppId?action=write-review');
      await launchUrl(url, mode: LaunchMode.externalApplication);
    }
  }
}