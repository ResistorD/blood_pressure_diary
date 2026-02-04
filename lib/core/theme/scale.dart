import 'dart:math' as math;
import 'package:flutter/widgets.dart';

const double _designHeight = 800.0; // эталонная высота макета (dp)

double _scale(BuildContext context) {
  final h = MediaQuery.sizeOf(context).height;
  final safeH = math.max(1.0, h);
  return safeH / _designHeight;
}

double dp(BuildContext context, double designPx) =>
    designPx * _scale(context);

double sp(BuildContext context, double designSp) =>
    designSp * _scale(context);
