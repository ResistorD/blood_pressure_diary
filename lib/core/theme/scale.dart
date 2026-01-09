import 'package:flutter/widgets.dart';

/// dp/sp scaling like in "frash":
/// base width = 360, clamp scale to [0.85..1.25]
double _uiScale(BuildContext context) {
  final w = MediaQuery.of(context).size.width;
  final s = w / 360.0;
  return s.clamp(0.85, 1.25).toDouble();
}

/// Density-independent pixels mapped to design pixels (Figma @ 360).
double dp(BuildContext context, double designPx) => designPx * _uiScale(context);

/// Scaled pixels for text.
double sp(BuildContext context, double designSp) => designSp * _uiScale(context);
