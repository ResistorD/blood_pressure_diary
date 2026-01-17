import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/theme/scale.dart';

import '../../profile/presentation/bloc/profile_cubit.dart';
import '../../profile/presentation/bloc/profile_state.dart';

import '../presentation/bloc/home_bloc.dart';
import '../presentation/bloc/home_state.dart';
import '../presentation/bloc/statistics_cubit.dart';
import '../presentation/bloc/statistics_state.dart';

enum _ChartTab { pressure, pulse }

class StatisticsScreen extends StatelessWidget {
  const StatisticsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<ProfileCubit, ProfileState>(
      builder: (context, profileState) {
        int targetSys = 120;
        int targetDia = 80;

        if (profileState is ProfileLoaded) {
          targetSys = profileState.profile.targetSystolic;
          targetDia = profileState.profile.targetDiastolic;
        }

        return BlocBuilder<HomeBloc, HomeState>(
          builder: (context, homeState) {
            if (homeState is! HomeLoaded) {
              return const Scaffold(body: Center(child: CircularProgressIndicator()));
            }

            return BlocProvider(
              create: (_) => StatisticsCubit(
                homeState.records,
                targetSystolic: targetSys,
                targetDiastolic: targetDia,
              )..updatePeriod(StatisticsPeriod.thirtyDays),
              child: const _StatisticsView(),
            );
          },
        );
      },
    );
  }
}

class _StatisticsView extends StatefulWidget {
  const _StatisticsView();

  @override
  State<_StatisticsView> createState() => _StatisticsViewState();
}

class _StatisticsViewState extends State<_StatisticsView> {
  _ChartTab _tab = _ChartTab.pressure;

  String _periodLabel(StatisticsPeriod p) {
    switch (p) {
      case StatisticsPeriod.sevenDays:
        return 'Неделя';
      case StatisticsPeriod.thirtyDays:
        return 'Месяц';
      case StatisticsPeriod.all:
        return 'Все';
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final shadows = context.appShadow;
    final text = context.appText;

    final headerH = dp(context, space.s128);
    final navH = dp(context, space.s72 - space.s2 - space.s1); // 69
    final side = dp(context, space.s20);

    final chipH = dp(context, space.s32);
    final chipW = dp(context, space.w96) + dp(context, space.s4) + dp(context, space.s1); // 101
    final chipR = dp(context, radii.r5);

    final tabsW = dp(context, space.w320);
    final tabsH = dp(context, space.s46);

    final chartW = dp(context, 322);
    final chartH = dp(context, 350);

    final statsW = dp(context, space.w320);
    final statsH = dp(context, space.s112);

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final cardBg = isDark ? AppPalette.dark700 : AppPalette.grey050;
    final chipBg = isDark ? AppPalette.dark700 : AppPalette.blue500;

    final headerTopInset = MediaQuery.paddingOf(context).top;

    final titleStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs26),
      fontWeight: text.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final tabSelectedStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs16),
      fontWeight: text.w600,
      color: isDark ? colors.textOnBrand : AppPalette.blue900,
      height: 1.0,
    );

    final tabUnselectedStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs16),
      fontWeight: text.w400,
      color: isDark ? AppPalette.dark350 : AppPalette.grey500,
      height: 1.0,
    );

    return Scaffold(
      backgroundColor: colors.background,
      body: BlocBuilder<StatisticsCubit, StatisticsState>(
        builder: (context, state) {
          final hasData = state.filteredRecords.isNotEmpty;

          return Column(
            children: [
              // Header
              Container(
                height: headerH,
                width: double.infinity,
                color: headerBg,
                padding: EdgeInsets.only(
                  left: side,
                  right: side,
                  top: headerTopInset + dp(context, space.s20),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        'Графики',
                        style: titleStyle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    _PeriodChip(
                      width: chipW,
                      height: chipH,
                      radius: chipR,
                      bg: chipBg,
                      textColor: colors.textOnBrand,
                      label: _periodLabel(state.period),
                      onSelected: (p) => context.read<StatisticsCubit>().updatePeriod(p),
                    ),
                  ],
                ),
              ),

              Expanded(
                child: SingleChildScrollView(
                  padding: EdgeInsets.only(
                    top: dp(context, space.s20),
                    bottom: navH + dp(context, space.s20),
                  ),
                  child: Column(
                    children: [
                      // Tabs card
                      Container(
                        width: tabsW,
                        height: tabsH,
                        decoration: BoxDecoration(
                          color: cardBg,
                          boxShadow: [shadows.card],
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: _WordUnderlineTab(
                                title: 'Давление',
                                selected: _tab == _ChartTab.pressure,
                                selectedStyle: tabSelectedStyle,
                                unselectedStyle: tabUnselectedStyle,
                                underlineColor: isDark ? colors.textOnBrand : AppPalette.blue900,
                                underlineHeight: dp(context, space.s2),
                                onTap: () => setState(() => _tab = _ChartTab.pressure),
                              ),
                            ),
                            Expanded(
                              child: _WordUnderlineTab(
                                title: 'Пульс',
                                selected: _tab == _ChartTab.pulse,
                                selectedStyle: tabSelectedStyle,
                                unselectedStyle: tabUnselectedStyle,
                                underlineColor: isDark ? colors.textOnBrand : AppPalette.blue900,
                                underlineHeight: dp(context, space.s2),
                                onTap: () => setState(() => _tab = _ChartTab.pulse),
                              ),
                            ),
                          ],
                        ),
                      ),

                      SizedBox(height: dp(context, space.s2)),

                      // Chart card
                      Container(
                        width: chartW,
                        height: chartH,
                        decoration: BoxDecoration(
                          color: cardBg,
                          boxShadow: [shadows.card],
                        ),
                        child: Padding(
                          padding: EdgeInsets.fromLTRB(
                            dp(context, space.s16),
                            dp(context, space.s16),
                            dp(context, space.s16),
                            dp(context, space.s20),
                          ),
                          child: hasData
                              ? _Chart(
                            tab: _tab,
                            state: state,
                            isDark: isDark,
                          )
                              : Center(
                            child: Text(
                              'Нет данных за этот период',
                              style: TextStyle(
                                fontFamily: text.family,
                                fontSize: sp(context, text.fs14),
                                fontWeight: text.w400,
                                color: isDark ? AppPalette.dark350 : AppPalette.grey500,
                                height: 1.0,
                              ),
                            ),
                          ),
                        ),
                      ),

                      SizedBox(height: dp(context, space.s20)),

                      // Stats
                      Container(
                        width: statsW,
                        height: statsH,
                        decoration: BoxDecoration(
                          color: cardBg,
                          boxShadow: [shadows.card],
                        ),
                        padding: EdgeInsets.symmetric(
                          horizontal: dp(context, space.s20),
                          vertical: dp(context, space.s16),
                        ),
                        child: _StatsBlock(
                          isDark: isDark,
                          tab: _tab,
                          state: state,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _PeriodChip extends StatelessWidget {
  final double width;
  final double height;
  final double radius;
  final Color bg;
  final Color textColor;
  final String label;
  final ValueChanged<StatisticsPeriod> onSelected;

  const _PeriodChip({
    required this.width,
    required this.height,
    required this.radius,
    required this.bg,
    required this.textColor,
    required this.label,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    final space = context.appSpace;
    final text = context.appText;

    return PopupMenuButton<StatisticsPeriod>(
      onSelected: onSelected,
      itemBuilder: (context) => const [
        PopupMenuItem(value: StatisticsPeriod.sevenDays, child: Text('Неделя')),
        PopupMenuItem(value: StatisticsPeriod.thirtyDays, child: Text('Месяц')),
        PopupMenuItem(value: StatisticsPeriod.all, child: Text('Все')),
      ],
      offset: Offset(0, dp(context, space.s30 - space.s2)),
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(radius),
        ),
        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s10)),
        child: Row(
          children: [
            Expanded(
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontFamily: text.family,
                  fontSize: sp(context, text.fs16),
                  fontWeight: text.w600,
                  color: textColor,
                  height: 1.0,
                ),
              ),
            ),
            SvgPicture.asset(
              'assets/arrow_drop_down.svg',
              width: dp(context, space.s24),
              height: dp(context, space.s24),
              colorFilter: ColorFilter.mode(textColor, BlendMode.srcIn),
            ),
          ],
        ),
      ),
    );
  }
}

class _WordUnderlineTab extends StatelessWidget {
  final String title;
  final bool selected;
  final TextStyle selectedStyle;
  final TextStyle unselectedStyle;
  final Color underlineColor;
  final double underlineHeight;
  final VoidCallback onTap;

  const _WordUnderlineTab({
    required this.title,
    required this.selected,
    required this.selectedStyle,
    required this.unselectedStyle,
    required this.underlineColor,
    required this.underlineHeight,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final space = context.appSpace;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Center(
        child: IntrinsicWidth(
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(title, style: selected ? selectedStyle : unselectedStyle),
              SizedBox(height: dp(context, space.s6)),
              Container(
                height: underlineHeight,
                width: double.infinity,
                color: selected ? underlineColor : Colors.transparent,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatsBlock extends StatelessWidget {
  final bool isDark;
  final _ChartTab tab;
  final StatisticsState state;

  const _StatsBlock({
    required this.isDark,
    required this.tab,
    required this.state,
  });

  @override
  Widget build(BuildContext context) {
    final space = context.appSpace;
    final text = context.appText;

    final color = isDark ? AppPalette.dark350 : AppPalette.blue900;

    String fmtPressure(double sys, double dia) => '${sys.toInt()}/${dia.toInt()}';
    String fmtPulse(double v) => v == 0 ? '—' : '${v.toInt()}';

    final avg = tab == _ChartTab.pressure ? fmtPressure(state.avgSys, state.avgDia) : fmtPulse(state.avgPulse);
    final max = tab == _ChartTab.pressure ? fmtPressure(state.maxSys, state.maxDia) : fmtPulse(state.maxPulse);
    final min = tab == _ChartTab.pressure ? fmtPressure(state.minSys, state.minDia) : fmtPulse(state.minPulse);

    Widget row(String label, String value) => Row(
      children: [
        Icon(Icons.favorite, size: dp(context, space.s20), color: color),
        SizedBox(width: dp(context, space.s16)),
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              fontFamily: text.family,
              fontSize: sp(context, text.fs16),
              fontWeight: text.w600,
              color: color,
              height: 1.0,
            ),
          ),
        ),
        Text(
          value,
          style: TextStyle(
            fontFamily: text.family,
            fontSize: sp(context, text.fs16),
            fontWeight: text.w600,
            color: color,
            height: 1.0,
          ),
        ),
      ],
    );

    return Column(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        row('Среднее:', avg),
        row('Макс.:', max),
        row('Мин.:', min),
      ],
    );
  }
}

class _Chart extends StatelessWidget {
  final _ChartTab tab;
  final StatisticsState state;
  final bool isDark;

  const _Chart({
    required this.tab,
    required this.state,
    required this.isDark,
  });

  int _xLabelStep(int len, StatisticsPeriod period) {
    if (len <= 1) return 1;
    if (period == StatisticsPeriod.sevenDays) return 1;

    if (period == StatisticsPeriod.thirtyDays) {
      if (len <= 10) return 1;
      if (len <= 20) return 2;
      return 4;
    }

    final target = 8;
    return (len / target).ceil().clamp(1, len);
  }

  Set<int> _pulseYLabels(double minY, double maxY) {
    int round10(double v) => (v / 10).round() * 10;
    final minR = (minY / 10).floor() * 10;
    final maxR = (maxY / 10).ceil() * 10;

    final span = (maxR - minR).abs();
    final rawStep = span / 3;
    var step = round10(rawStep.toDouble()).abs();
    if (step < 10) step = 10;

    return {minR, minR + step, minR + step * 2, maxR};
  }

  @override
  Widget build(BuildContext context) {
    final space = context.appSpace;
    final text = context.appText;
    final colors = context.appColors;

    final all = state.filteredRecords;
    final records = tab == _ChartTab.pulse ? all.where((r) => r.pulse > 0).toList() : all;

    if (records.isEmpty) {
      return Center(
        child: Text(
          'Нет данных',
          style: TextStyle(
            fontFamily: text.family,
            fontSize: sp(context, text.fs14),
            fontWeight: text.w400,
            color: isDark ? AppPalette.dark350 : AppPalette.grey500,
            height: 1.0,
          ),
        ),
      );
    }

    const pressureGridStep = 40.0;
    const pulseGridStep = 10.0;

    double minY;
    double maxY;

    if (tab == _ChartTab.pressure) {
      // фиксируем разумный диапазон как в макете
      minY = 40;
      maxY = 220;
    } else {
      final minP = records.map((e) => e.pulse).reduce((a, b) => a < b ? a : b).toDouble();
      final maxP = records.map((e) => e.pulse).reduce((a, b) => a > b ? a : b).toDouble();
      minY = (minP - 10).clamp(30, 220);
      maxY = (maxP + 10).clamp(60, 240);
    }

    final gridColor = isDark ? AppPalette.dark600.withValues(alpha: 0.25) : AppPalette.grey400.withValues(alpha: 0.7);
    final axisTextColor = isDark ? AppPalette.dark350 : AppPalette.blue900;

    final lineStrong = isDark ? AppPalette.dark350 : AppPalette.blue900;
    final lineSoft = isDark ? AppPalette.blue500 : AppPalette.blue500;

    final spotsA = records.asMap().entries.map((e) {
      final x = e.key.toDouble();
      final y = tab == _ChartTab.pressure ? e.value.systolic.toDouble() : e.value.pulse.toDouble();
      return FlSpot(x, y);
    }).toList();

    final spotsB = tab == _ChartTab.pressure
        ? records.asMap().entries.map((e) => FlSpot(e.key.toDouble(), e.value.diastolic.toDouble())).toList()
        : const <FlSpot>[];

    final pressureYLabels = <int>{80, 120, 160, 200};
    final pulseYLabels = _pulseYLabels(minY, maxY);
    final xStep = _xLabelStep(records.length, state.period);

    String xLabel(DateTime dt) => DateFormat('d', 'ru').format(dt);

    // tooltip style
    final tooltipBg = isDark ? AppPalette.dark900.withValues(alpha: 0.92) : AppPalette.grey050.withValues(alpha: 0.96);
    final tooltipTextColor = isDark ? Colors.white : AppPalette.blue900;

    // ✅ зона давления из профиля
    final yLow = state.targetDiastolic.toDouble();
    final yHigh = state.targetSystolic.toDouble();
    final zoneColor = (tab == _ChartTab.pressure)
        ? (isDark ? AppPalette.blueAccent.withValues(alpha: 0.10) : AppPalette.blueAccent.withValues(alpha: 0.12))
        : Colors.transparent;

    final zoneLineColor = isDark
        ? AppPalette.dark350.withValues(alpha: 0.45)
        : AppPalette.blue900.withValues(alpha: 0.35);

    return LineChart(
      LineChartData(
        // ✅ ZONE (полоса)
        rangeAnnotations: tab == _ChartTab.pressure
            ? RangeAnnotations(
          horizontalRangeAnnotations: [
            HorizontalRangeAnnotation(
              y1: yLow,
              y2: yHigh,
              color: zoneColor,
            ),
          ],
        )
            : const RangeAnnotations(),

        // ✅ границы зоны пунктиром
        extraLinesData: tab == _ChartTab.pressure
            ? ExtraLinesData(
          horizontalLines: [
            HorizontalLine(
              y: yHigh,
              color: zoneLineColor,
              strokeWidth: 1,
              dashArray: const [6, 6],
            ),
            HorizontalLine(
              y: yLow,
              color: zoneLineColor,
              strokeWidth: 1,
              dashArray: const [6, 6],
            ),
          ],
        )
            : ExtraLinesData(horizontalLines: const []),

    gridData: FlGridData(
          show: true,
          drawVerticalLine: true,
          horizontalInterval: tab == _ChartTab.pressure ? pressureGridStep : pulseGridStep,
          verticalInterval: 1,
          getDrawingHorizontalLine: (_) => FlLine(color: gridColor, strokeWidth: 1),
          getDrawingVerticalLine: (_) => FlLine(color: gridColor, strokeWidth: 1),
        ),
        titlesData: FlTitlesData(
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: dp(context, space.s40),
              interval: tab == _ChartTab.pressure ? pressureGridStep : pulseGridStep,
              getTitlesWidget: (value, meta) {
                final v = value.toInt();
                if (tab == _ChartTab.pressure) {
                  if (!pressureYLabels.contains(v)) return const SizedBox.shrink();
                } else {
                  if (!pulseYLabels.contains(v)) return const SizedBox.shrink();
                }
                return Text(
                  v.toString(),
                  style: TextStyle(
                    fontFamily: text.family,
                    fontSize: sp(context, text.fs12),
                    fontWeight: text.w400,
                    color: axisTextColor,
                    height: 1.0,
                  ),
                );
              },
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: dp(context, space.s24),
              interval: 1,
              getTitlesWidget: (value, meta) {
                final i = value.toInt();
                if (i < 0 || i >= records.length) return const SizedBox.shrink();
                if (i % xStep != 0 && i != records.length - 1) return const SizedBox.shrink();
                return Padding(
                  padding: EdgeInsets.only(top: dp(context, space.s6)),
                  child: Text(
                    xLabel(records[i].dateTime),
                    style: TextStyle(
                      fontFamily: text.family,
                      fontSize: sp(context, text.fs12),
                      fontWeight: text.w400,
                      color: axisTextColor,
                      height: 1.0,
                    ),
                  ),
                );
              },
            ),
          ),
        ),
        borderData: FlBorderData(show: false),
        minX: 0,
        maxX: (records.length - 1).toDouble(),
        minY: minY,
        maxY: maxY,
        lineBarsData: [
          LineChartBarData(
            spots: spotsA,
            isCurved: false,
            color: lineStrong,
            barWidth: dp(context, space.s2),
            dotData: const FlDotData(show: false),
          ),
          if (tab == _ChartTab.pressure)
            LineChartBarData(
              spots: spotsB,
              isCurved: false,
              color: lineSoft,
              barWidth: dp(context, space.s2),
              dotData: const FlDotData(show: false),
            ),
        ],
        lineTouchData: LineTouchData(
          enabled: true,
          handleBuiltInTouches: true,
          touchTooltipData: LineTouchTooltipData(
            getTooltipColor: (_) => tooltipBg,
            tooltipRoundedRadius: dp(context, context.appRadii.r10),
            tooltipPadding: EdgeInsets.symmetric(
              horizontal: dp(context, space.s10),
              vertical: dp(context, space.s6),
            ),
            fitInsideHorizontally: true,
            fitInsideVertically: true,
            getTooltipItems: (touchedSpots) {
              return touchedSpots.map((spot) {
                final rec = records[spot.x.toInt()];
                final dateStr = DateFormat('dd.MM', 'ru').format(rec.dateTime);
                final label = tab == _ChartTab.pressure ? (spot.barIndex == 0 ? 'Сист.' : 'Диаст.') : 'Пульс';
                return LineTooltipItem(
                  '$dateStr\n$label: ${spot.y.toInt()}',
                  TextStyle(
                    fontFamily: text.family,
                    fontSize: sp(context, text.fs12),
                    fontWeight: text.w600,
                    color: tooltipTextColor,
                    height: 1.1,
                  ),
                );
              }).toList();
            },
          ),
        ),
      ),
    );
  }
}
