import 'dart:math' as math;
import 'package:flutter/widgets.dart';

/// Responsive scale used to match Figma design (base width = 360).
///
/// Why:
/// - Your Figma layouts are authored for 360px width.
/// - Many real devices have logical width > 360dp (e.g. 393/411).
/// - Scaling sizes by width/360 makes UI match how you expect it to look
///   on your actual device.
///
/// IMPORTANT:
/// - No clamp. Clamp is what causes "mysterious" drift and inconsistent feel.
/// - If you later want special rules for tablets, we can add them explicitly.

const double _designWidth = 360.0;

double _scale(BuildContext context) {
  final w = MediaQuery.sizeOf(context).width;
  // Guard against weird zeros in early layout phases
  final safeW = math.max(1.0, w);
  return safeW / _designWidth;
}

double dp(BuildContext context, double designPx) => designPx * _scale(context);

double sp(BuildContext context, double designSp) => designSp * _scale(context);
