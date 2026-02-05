import 'package:url_launcher/url_launcher.dart';
import 'dart:io' show Platform;

Future<void> launchEmail({
  required String to,
  required String subject,
  String? body,
}) async {
  final uri = Uri(
    scheme: 'mailto',
    path: to,
    queryParameters: <String, String>{
      'subject': subject,
      if (body != null && body.trim().isNotEmpty) 'body': body,
    },
  );

  if (!await launchUrl(uri, mode: LaunchMode.externalApplication)) {
    // можно показать SnackBar/Toast — как у тебя принято в проекте
    throw Exception('Could not launch email client');
  }
}

Future<void> rateApp({
  required String androidPackageName,
  String? iosAppId, // когда появится
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
    if (iosAppId == null || iosAppId.isEmpty) {
      // пока не опубликовано — можно просто молча игнорить или показать подсказку
      throw Exception('iOS App ID is not set yet');
    }
    final uri = Uri.parse('https://apps.apple.com/app/id$iosAppId?action=write-review');
    await launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}