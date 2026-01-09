import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:intl/intl.dart';
import '../../../../core/theme/app_theme.dart';
import 'bloc/home_bloc.dart';
import 'bloc/home_state.dart';
import 'bloc/statistics_cubit.dart';
import 'bloc/statistics_state.dart';

import '../../profile/presentation/bloc/profile_cubit.dart';
import '../../profile/presentation/bloc/profile_state.dart';

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
            if (homeState is HomeLoaded) {
              return BlocProvider(
                create: (context) => StatisticsCubit(
                  homeState.records,
                  targetSystolic: targetSys,
                  targetDiastolic: targetDia,
                ),
                child: const _StatisticsView(),
              );
            }
            return const Scaffold(
              body: Center(child: CircularProgressIndicator()),
            );
          },
        );
      },
    );
  }
}

class _StatisticsView extends StatelessWidget {
  const _StatisticsView();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppUI.background,
      appBar: AppBar(
        title: const Text('Графики',
            style: TextStyle(
                color: Colors.black,
                fontFamily: 'Inter',
                fontWeight: FontWeight.bold)),
        backgroundColor: Colors.white,
        elevation: 0,
        centerTitle: false,
      ),
      body: BlocBuilder<StatisticsCubit, StatisticsState>(
        builder: (context, state) {
          if (state.filteredRecords.isEmpty) {
            return const Center(child: Text("Нет данных за этот период"));
          }

          return SingleChildScrollView(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              children: [
                _buildAnalyticsCards(state),
                const SizedBox(height: 24),
                _PressureChart(state: state),
                const SizedBox(height: 24),
                _buildPeriodSelector(context, state.period),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildAnalyticsCards(StatisticsState state) {
    return Row(
      children: [
        _AnalyticsCard(
          title: "Мин",
          sys: state.minSys.toInt(),
          dia: state.minDia.toInt(),
          color: Colors.blueAccent,
        ),
        const SizedBox(width: 12),
        _AnalyticsCard(
          title: "Сред",
          sys: state.avgSys.toInt(),
          dia: state.avgDia.toInt(),
          color: Colors.green,
        ),
        const SizedBox(width: 12),
        _AnalyticsCard(
          title: "Макс",
          sys: state.maxSys.toInt(),
          dia: state.maxDia.toInt(),
          color: Colors.redAccent,
        ),
      ],
    );
  }

  Widget _buildPeriodSelector(BuildContext context, StatisticsPeriod current) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [AppUI.shadow4x2],
      ),
      child: Row(
        children: [
          _PeriodButton(
            title: "7 дней",
            isSelected: current == StatisticsPeriod.sevenDays,
            onTap: () => context
                .read<StatisticsCubit>()
                .updatePeriod(StatisticsPeriod.sevenDays),
          ),
          _PeriodButton(
            title: "30 дней",
            isSelected: current == StatisticsPeriod.thirtyDays,
            onTap: () => context
                .read<StatisticsCubit>()
                .updatePeriod(StatisticsPeriod.thirtyDays),
          ),
          _PeriodButton(
            title: "Все",
            isSelected: current == StatisticsPeriod.all,
            onTap: () => context
                .read<StatisticsCubit>()
                .updatePeriod(StatisticsPeriod.all),
          ),
        ],
      ),
    );
  }
}

class _AnalyticsCard extends StatelessWidget {
  final String title;
  final int sys;
  final int dia;
  final Color color;

  const _AnalyticsCard({
    required this.title,
    required this.sys,
    required this.dia,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          boxShadow: [AppUI.shadow4x2],
        ),
        child: Column(
          children: [
            Text(title,
                style: TextStyle(
                    fontSize: 12, color: Colors.grey[600], fontFamily: 'Inter')),
            const SizedBox(height: 4),
            Text("$sys/$dia",
                style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.bold,
                    color: color,
                    fontFamily: 'Inter')),
          ],
        ),
      ),
    );
  }
}

class _PeriodButton extends StatelessWidget {
  final String title;
  final bool isSelected;
  final VoidCallback onTap;

  const _PeriodButton({
    required this.title,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: GestureDetector(
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: isSelected ? AppUI.primaryBlue : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Center(
            child: Text(
              title,
              style: TextStyle(
                color: isSelected ? Colors.white : Colors.grey[600],
                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                fontFamily: 'Inter',
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PressureChart extends StatelessWidget {
  final StatisticsState state;
  const _PressureChart({required this.state});

  @override
  Widget build(BuildContext context) {
    final records = state.filteredRecords;
    
    final spotsSys = records.asMap().entries.map((e) {
      return FlSpot(e.key.toDouble(), e.value.systolic.toDouble());
    }).toList();

    final spotsDia = records.asMap().entries.map((e) {
      return FlSpot(e.key.toDouble(), e.value.diastolic.toDouble());
    }).toList();

    return Container(
      height: 350,
      padding: const EdgeInsets.only(right: 16, top: 16, bottom: 8),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(16),
        boxShadow: [AppUI.shadow4x2],
      ),
      child: LineChart(
        LineChartData(
          gridData: FlGridData(
            show: true,
            drawVerticalLine: false,
            horizontalInterval: 20,
            getDrawingHorizontalLine: (value) {
              return FlLine(
                color: Colors.grey.withOpacity(0.1),
                strokeWidth: 1,
              );
            },
          ),
          titlesData: FlTitlesData(
            bottomTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true,
                getTitlesWidget: (value, meta) {
                  final index = value.toInt();
                  if (index >= 0 && index < records.length) {
                    if (index == 0 || index == records.length - 1 || (records.length > 5 && index % (records.length ~/ 4) == 0)) {
                      return Padding(
                        padding: const EdgeInsets.only(top: 8.0),
                        child: Text(
                          DateFormat('d.MM').format(records[index].dateTime),
                          style: TextStyle(fontSize: 10, color: Colors.grey[600]),
                        ),
                      );
                    }
                  }
                  return const SizedBox.shrink();
                },
                interval: 1,
              ),
            ),
            leftTitles: AxisTitles(
              sideTitles: SideTitles(
                showTitles: true, 
                reservedSize: 40,
                getTitlesWidget: (value, meta) {
                  return Text(value.toInt().toString(),
                    style: TextStyle(fontSize: 10, color: Colors.grey[600]));
                }
              ),
            ),
            topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
            rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          ),
          borderData: FlBorderData(show: false),
          minX: 0,
          maxX: (records.length - 1).toDouble(),
          minY: 40,
          maxY: 200,
          extraLinesData: ExtraLinesData(
            horizontalLines: [
              HorizontalLine(
                y: state.targetSystolic.toDouble(),
                color: Colors.redAccent.withOpacity(0.5),
                strokeWidth: 1,
                dashArray: [5, 5],
                label: HorizontalLineLabel(
                  show: true,
                  alignment: Alignment.topRight,
                  padding: const EdgeInsets.only(right: 5, bottom: 2),
                  style: const TextStyle(fontSize: 9, color: Colors.redAccent),
                  labelResolver: (line) => '${state.targetSystolic}',
                ),
              ),
              HorizontalLine(
                y: state.targetDiastolic.toDouble(),
                color: Colors.blueAccent.withOpacity(0.5),
                strokeWidth: 1,
                dashArray: [5, 5],
                label: HorizontalLineLabel(
                  show: true,
                  alignment: Alignment.topRight,
                  padding: const EdgeInsets.only(right: 5, bottom: 2),
                  style: const TextStyle(fontSize: 9, color: Colors.blueAccent),
                  labelResolver: (line) => '${state.targetDiastolic}',
                ),
              ),
            ],
          ),
          lineBarsData: [
            LineChartBarData(
              spots: spotsSys,
              isCurved: true,
              color: Colors.redAccent,
              barWidth: 3,
              isStrokeCapRound: true,
              dotData: FlDotData(
                show: true,
                getDotPainter: (spot, percent, barData, index) => FlDotCirclePainter(
                  radius: 3,
                  color: Colors.white,
                  strokeWidth: 2,
                  strokeColor: Colors.redAccent,
                ),
              ),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  colors: [
                    Colors.redAccent.withOpacity(0.2),
                    Colors.redAccent.withOpacity(0.0),
                  ],
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                ),
              ),
            ),
            LineChartBarData(
              spots: spotsDia,
              isCurved: true,
              color: Colors.blueAccent,
              barWidth: 3,
              isStrokeCapRound: true,
              dotData: FlDotData(
                show: true,
                getDotPainter: (spot, percent, barData, index) => FlDotCirclePainter(
                  radius: 3,
                  color: Colors.white,
                  strokeWidth: 2,
                  strokeColor: Colors.blueAccent,
                ),
              ),
              belowBarData: BarAreaData(
                show: true,
                gradient: LinearGradient(
                  colors: [
                    Colors.blueAccent.withOpacity(0.2),
                    Colors.blueAccent.withOpacity(0.0),
                  ],
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                ),
              ),
            ),
          ],
          lineTouchData: LineTouchData(
            touchTooltipData: LineTouchTooltipData(
              getTooltipColor: (touchedSpot) => Colors.blueGrey.withOpacity(0.8),
              getTooltipItems: (touchedSpots) {
                return touchedSpots.map((spot) {
                  final record = records[spot.x.toInt()];
                  final dateStr = DateFormat('dd.MM HH:mm').format(record.dateTime);
                  return LineTooltipItem(
                    '$dateStr\n${spot.y.toInt()} mmHg',
                    const TextStyle(color: Colors.white, fontSize: 10),
                  );
                }).toList();
              },
            ),
          ),
        ),
      ),
    );
  }
}
