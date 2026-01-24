import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/theme/scale.dart';

import '../data/blood_pressure_model.dart';
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
    return BlocProvider(
      create: (context) {
        final homeState = context.read<HomeBloc>().state;
        final profileState = context.read<ProfileCubit>().state;
        final records = homeState is HomeLoaded ? homeState.records : const <BloodPressureRecord>[];
        final targetSys = profileState is ProfileLoaded ? profileState.profile.targetSystolic : 120;
        final targetDia = profileState is ProfileLoaded ? profileState.profile.targetDiastolic : 80;
        return StatisticsCubit(
          records,
          targetSystolic: targetSys,
          targetDiastolic: targetDia,
        )..updatePeriod(StatisticsPeriod.thirtyDays);
      },
      child: MultiBlocListener(
        listeners: [
          BlocListener<HomeBloc, HomeState>(
            listener: (context, homeState) {
              if (homeState is HomeLoaded) {
                context.read<StatisticsCubit>().updateRecords(homeState.records);
              }
            },
          ),
          BlocListener<ProfileCubit, ProfileState>(
            listener: (context, profileState) {
              if (profileState is ProfileLoaded) {
                context.read<StatisticsCubit>().updateTargets(
                  targetSystolic: profileState.profile.targetSystolic,
                  targetDiastolic: profileState.profile.targetDiastolic,
                );
              }
            },
          ),
        ],
        child: BlocBuilder<HomeBloc, HomeState>(
          builder: (context, homeState) {
            if (homeState is! HomeLoaded) {
              return const Scaffold(body: Center(child: CircularProgressIndicator()));
            }

            return const _StatisticsView();
          },
        ),
      ),
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
                          padding: EdgeInsets.only(
                            left: dp(context, space.s16),
                            right: dp(context, space.s16),
                            top: dp(context, space.s16),
                            bottom: dp(context, space.s8),
                          ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                _tab == _ChartTab.pressure ? 'Артериальное давление' : 'Пульс',
                                style: TextStyle(
                                  fontFamily: text.family,
                                  fontSize: sp(context, text.fs16),
                                  fontWeight: text.w600,
                                  color: colors.textPrimary,
                                  height: 1.0,
                                ),
                              ),
                              SizedBox(height: dp(context, space.s8)),
                              Expanded(
                                child: hasData
                                    ? _Chart(
                                        records: state.filteredRecords,
                                        showPressure: _tab == _ChartTab.pressure,
                                        targetSystolic: state.targetSystolic,
                                        targetDiastolic: state.targetDiastolic,
                                      )
                                    : Center(
                                        child: Text(
                                          'Нет данных',
                                          style: TextStyle(
                                            fontFamily: text.family,
                                            fontSize: sp(context, text.fs14),
                                            fontWeight: text.w400,
                                            color: colors.textSecondary,
                                          ),
                                        ),
                                      ),
                              ),
                            ],
                          ),
                        ),
                      ),

                      SizedBox(height: dp(context, space.s12)),

                      // Stats
                      SizedBox(
                        width: statsW,
                        height: statsH,
                        child: _StatsBlock(
                          state: state,
                          cardBg: cardBg,
                          shadows: shadows,
                          text: text,
                          colors: colors,
                        ),
                      ),

                      SizedBox(height: dp(context, space.s12)),
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
    final text = context.appText;
    final space = context.appSpace;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _showPeriodMenu(context),
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(radius),
        ),
        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
        alignment: Alignment.center,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(
              label,
              style: TextStyle(
                fontFamily: text.family,
                fontSize: sp(context, text.fs14),
                fontWeight: text.w600,
                color: textColor,
                height: 1.0,
              ),
            ),
            Icon(
              Icons.keyboard_arrow_down,
              size: dp(context, space.s20),
              color: textColor,
            ),
          ],
        ),
      ),
    );
  }

  void _showPeriodMenu(BuildContext context) async {
    final selected = await showModalBottomSheet<StatisticsPeriod>(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        final colors = context.appColors;
        final space = context.appSpace;
        final radii = context.appRadii;
        final text = context.appText;

        final sheetBg = colors.surface;
        final sheetR = dp(context, radii.r10);

        Widget item(String title, StatisticsPeriod period) {
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => Navigator.pop(ctx, period),
            child: Container(
              height: dp(context, space.s48),
              decoration: BoxDecoration(
                color: colors.surfaceAlt,
                borderRadius: BorderRadius.circular(dp(context, radii.r10)),
              ),
              padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
              alignment: Alignment.centerLeft,
              child: Text(
                title,
                style: TextStyle(
                  fontFamily: text.family,
                  fontSize: sp(context, text.fs18),
                  fontWeight: text.w500,
                  color: colors.textPrimary,
                ),
              ),
            ),
          );
        }

        return SafeArea(
          child: Padding(
            padding: EdgeInsets.all(dp(context, space.s12)),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: sheetBg,
                borderRadius: BorderRadius.circular(sheetR),
                boxShadow: [context.appShadow.card],
              ),
              child: Padding(
                padding: EdgeInsets.all(dp(context, space.s12)),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    item('Неделя', StatisticsPeriod.sevenDays),
                    SizedBox(height: dp(context, space.s8)),
                    item('Месяц', StatisticsPeriod.thirtyDays),
                    SizedBox(height: dp(context, space.s8)),
                    item('Все', StatisticsPeriod.all),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );

    if (selected != null) {
      onSelected(selected);
    }
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
      child: Container(
        alignment: Alignment.center,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(title, style: selected ? selectedStyle : unselectedStyle),
            SizedBox(height: dp(context, space.s8)),
            if (selected)
              Container(
                height: underlineHeight,
                width: dp(context, space.s56),
                color: underlineColor,
              ),
          ],
        ),
      ),
    );
  }
}

class _Chart extends StatelessWidget {
  final List<BloodPressureRecord> records;
  final bool showPressure;
  final int targetSystolic;
  final int targetDiastolic;

  const _Chart({
    required this.records,
    required this.showPressure,
    required this.targetSystolic,
    required this.targetDiastolic,
  });

  @override
  Widget build(BuildContext context) {
    if (records.isEmpty) {
      return const SizedBox.shrink();
    }

    final isDark = Theme.of(context).brightness == Brightness.dark;
    final colors = context.appColors;
    final space = context.appSpace;

    final spotsSys = <FlSpot>[];
    final spotsDia = <FlSpot>[];
    final spotsPulse = <FlSpot>[];

    for (int i = 0; i < records.length; i++) {
      final r = records[i];
      spotsSys.add(FlSpot(i.toDouble(), r.systolic.toDouble()));
      spotsDia.add(FlSpot(i.toDouble(), r.diastolic.toDouble()));
      spotsPulse.add(FlSpot(i.toDouble(), r.pulse.toDouble()));
    }

    final lineColorSys = isDark ? colors.textOnBrand : AppPalette.blue900;
    final lineColorDia = isDark ? colors.textOnBrand : AppPalette.blue500;
    final lineColorPulse = isDark ? colors.textOnBrand : AppPalette.blue700;

    final refLineColor = isDark ? colors.textOnBrand.withValues(alpha: 0.35) : AppPalette.blue700;

    final textStyle = TextStyle(
      fontFamily: context.appText.family,
      fontSize: sp(context, context.appText.fs10),
      color: colors.textSecondary,
    );

    final axisColor = isDark ? colors.textOnBrand.withValues(alpha: 0.6) : AppPalette.grey300;

    final gridColor = isDark ? colors.textOnBrand.withValues(alpha: 0.1) : AppPalette.grey200;

    return LineChart(
      LineChartData(
        minX: 0,
        maxX: records.length.toDouble() - 1,
        minY: 0,
        maxY: showPressure ? 200 : 150,
        lineTouchData: LineTouchData(
          enabled: true,
          touchTooltipData: LineTouchTooltipData(
            tooltipBgColor: colors.surface,
            tooltipRoundedRadius: dp(context, space.s8),
            tooltipBorder: BorderSide(color: colors.textPrimary.withValues(alpha: 0.1)),
          ),
        ),
        gridData: FlGridData(
          show: true,
          drawVerticalLine: false,
          horizontalInterval: 20,
          getDrawingHorizontalLine: (_) => FlLine(color: gridColor, strokeWidth: dp(context, space.s1)),
        ),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              interval: 20,
              reservedSize: dp(context, space.s32),
              getTitlesWidget: (value, meta) {
                return Text(value.toInt().toString(), style: textStyle);
              },
            ),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              interval: 2,
              getTitlesWidget: (value, meta) {
                final index = value.toInt();
                if (index < 0 || index >= records.length) return const SizedBox.shrink();
                final date = records[index].dateTime;
                return Text(DateFormat('dd.MM').format(date), style: textStyle);
              },
            ),
          ),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        borderData: FlBorderData(
          show: true,
          border: Border(
            bottom: BorderSide(color: axisColor, width: dp(context, space.s1)),
            left: BorderSide(color: axisColor, width: dp(context, space.s1)),
          ),
        ),
        lineBarsData: showPressure
            ? [
                LineChartBarData(
                  spots: spotsSys,
                  isCurved: true,
                  color: lineColorSys,
                  barWidth: dp(context, space.s2),
                  dotData: const FlDotData(show: false),
                ),
                LineChartBarData(
                  spots: spotsDia,
                  isCurved: true,
                  color: lineColorDia,
                  barWidth: dp(context, space.s2),
                  dotData: const FlDotData(show: false),
                ),
              ]
            : [
                LineChartBarData(
                  spots: spotsPulse,
                  isCurved: true,
                  color: lineColorPulse,
                  barWidth: dp(context, space.s2),
                  dotData: const FlDotData(show: false),
                ),
              ],
        extraLinesData: showPressure
            ? ExtraLinesData(
                horizontalLines: [
                  HorizontalLine(
                    y: targetSystolic.toDouble(),
                    color: refLineColor,
                    strokeWidth: dp(context, space.s1),
                    dashArray: [dp(context, space.s4).toInt(), dp(context, space.s4).toInt()],
                  ),
                  HorizontalLine(
                    y: targetDiastolic.toDouble(),
                    color: refLineColor,
                    strokeWidth: dp(context, space.s1),
                    dashArray: [dp(context, space.s4).toInt(), dp(context, space.s4).toInt()],
                  ),
                ],
              )
            : null,
      ),
    );
  }
}

class _StatsBlock extends StatelessWidget {
  final StatisticsState state;
  final Color cardBg;
  final AppShadow shadows;
  final AppText text;
  final AppColors colors;

  const _StatsBlock({
    required this.state,
    required this.cardBg,
    required this.shadows,
    required this.text,
    required this.colors,
  });

  @override
  Widget build(BuildContext context) {
    final space = context.appSpace;

    TextStyle labelStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs12),
      fontWeight: text.w400,
      color: colors.textSecondary,
      height: 1.0,
    );

    TextStyle valueStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs20),
      fontWeight: text.w600,
      color: colors.textPrimary,
      height: 1.0,
    );

    Widget rowItem(String label, String value) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(label, style: labelStyle),
          SizedBox(height: dp(context, space.s4)),
          Text(value, style: valueStyle),
        ],
      );
    }

    String fmt(double v) => v.toStringAsFixed(0);

    return Container(
      decoration: BoxDecoration(
        color: cardBg,
        boxShadow: [shadows.card],
      ),
      padding: EdgeInsets.all(dp(context, space.s16)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              rowItem('Максимум', fmt(state.maxSys)),
              rowItem('Среднее', fmt(state.avgSys)),
              rowItem('Минимум', fmt(state.minSys)),
            ],
          ),
          SizedBox(height: dp(context, space.s8)),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              rowItem('Диаст', fmt(state.maxDia)),
              rowItem('Диаст', fmt(state.avgDia)),
              rowItem('Диаст', fmt(state.minDia)),
            ],
          ),
          SizedBox(height: dp(context, space.s8)),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              rowItem('Пульс', fmt(state.maxPulse)),
              rowItem('Пульс', fmt(state.avgPulse)),
              rowItem('Пульс', fmt(state.minPulse)),
            ],
          ),
        ],
      ),
    );
  }
}
