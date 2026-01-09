import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/scale.dart';
import '../../../../core/utils/app_strings.dart';
import '../data/blood_pressure_model.dart';
import 'bloc/home_bloc.dart';
import 'bloc/home_state.dart';
import 'widgets/summary_card.dart';
import 'widgets/record_list_item.dart';
import '../../add_record/presentation/add_record_screen.dart';

enum _FilterPeriod { today, week, month, all }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  _FilterPeriod _period = _FilterPeriod.week;

  String _periodLabel(_FilterPeriod p) {
    switch (p) {
      case _FilterPeriod.today:
        return AppStrings.today;
      case _FilterPeriod.week:
        return AppStrings.week;
      case _FilterPeriod.month:
        return AppStrings.month;
      case _FilterPeriod.all:
        return AppStrings.allShort;
    }
  }

  String _recordsWord(int n) => AppStrings.recordsWord(n);

  List<BloodPressureRecord> _applyFilter(List<BloodPressureRecord> records) {
    final now = DateTime.now();
    switch (_period) {
      case _FilterPeriod.today:
        final d = DateTime(now.year, now.month, now.day);
        return records.where((r) {
          final rd = DateTime(r.dateTime.year, r.dateTime.month, r.dateTime.day);
          return rd == d;
        }).toList();
      case _FilterPeriod.week:
        final from = now.subtract(const Duration(days: 7));
        return records.where((r) => r.dateTime.isAfter(from)).toList();
      case _FilterPeriod.month:
        final from = now.subtract(const Duration(days: 30));
        return records.where((r) => r.dateTime.isAfter(from)).toList();
      case _FilterPeriod.all:
        return records;
    }
  }

  void _openEdit(BuildContext context, BloodPressureRecord record) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => AddRecordScreen(record: record)));
  }

  @override
  Widget build(BuildContext context) {
    final safeTop = MediaQuery.of(context).padding.top;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    // ===== Figma palette (light/dark) =====
    final bg = isDark ? const Color(0xFF2D2D2D) : const Color(0xFFF0F4F8);
    final headerBg = isDark ? const Color(0xFF2D2D2D) : const Color(0xFF4D83AC);
    final shelfBg = isDark ? const Color(0xFF2D2D2D) : const Color(0xFFF9F8FA);
    final shelfDivider = isDark ? Colors.transparent : const Color(0x33000000);

    final titleColor = Colors.white;
    final countColor = isDark ? const Color(0xFFCCCCCC) : const Color(0xFFBFD4E7);

    final dateColor = isDark ? const Color(0xFFCCCCCC) : const Color(0xFF325674);

    final filterChipBg = isDark ? const Color(0xFF4C4C4C) : Colors.white.withValues(alpha: 0.15);
    final filterChipRadius = dp(context, 5);

    // ===== Figma sizing =====
    final blueH = dp(context, 169);
    final lightH = dp(context, 82);
    final overlap = dp(context, 50);

    final side = dp(context, 20);

    final titleFont = sp(context, 26);
    final filterFont = sp(context, 16);

    return BlocBuilder<HomeBloc, HomeState>(
      builder: (context, state) {
        final all = state is HomeLoaded ? state.records : const <BloodPressureRecord>[];
        final records = _applyFilter(all)..sort((a, b) => b.dateTime.compareTo(a.dateTime));
        final filteredCount = records.length;

        final lastRecord = all.isNotEmpty
            ? (List<BloodPressureRecord>.from(all)..sort((a, b) => b.dateTime.compareTo(a.dateTime))).first
            : null;

        final groups = _groupByDate(records);

        final header = SizedBox(
          height: blueH + lightH,
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              // Header background
              Positioned.fill(child: ColoredBox(color: headerBg)),

              // Light shelf (in dark it becomes same bg, divider hidden)
              Positioned(
                left: 0,
                right: 0,
                top: blueH,
                height: lightH,
                child: Stack(
                  children: [
                    Positioned.fill(child: ColoredBox(color: shelfBg)),
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom: 0,
                      height: 0.5,
                      child: ColoredBox(color: shelfDivider),
                    ),
                  ],
                ),
              ),

              // Title + count + filter
              Positioned(
                left: side,
                right: side,
                top: safeTop + dp(context, 20),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            AppStrings.myDiary,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: titleColor,
                              fontSize: titleFont,
                              fontWeight: FontWeight.w600,
                              fontFamily: 'Inter',
                              height: 1.0,
                            ),
                          ),
                          SizedBox(height: dp(context, 20)),
                          Text(
                            '$filteredCount ${_recordsWord(filteredCount)}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              color: countColor,
                              fontSize: sp(context, 16),
                              fontWeight: FontWeight.w500,
                              fontFamily: 'Inter',
                              height: 1.0,
                            ),
                          ),
                        ],
                      ),
                    ),
                    PopupMenuButton<_FilterPeriod>(
                      onSelected: (value) => setState(() => _period = value),
                      itemBuilder: (context) => const [
                        PopupMenuItem(value: _FilterPeriod.today, child: Text(AppStrings.today)),
                        PopupMenuItem(value: _FilterPeriod.week, child: Text(AppStrings.week)),
                        PopupMenuItem(value: _FilterPeriod.month, child: Text(AppStrings.month)),
                        PopupMenuItem(value: _FilterPeriod.all, child: Text(AppStrings.allTime)),
                      ],
                      offset: Offset(0, dp(context, 28)),
                      child: Container(
                        height: dp(context, 32),
                        padding: EdgeInsets.symmetric(horizontal: dp(context, 10)),
                        decoration: BoxDecoration(
                          color: filterChipBg,
                          borderRadius: BorderRadius.circular(filterChipRadius),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _periodLabel(_period),
                              style: TextStyle(
                                color: titleColor,
                                fontSize: filterFont,
                                fontWeight: FontWeight.w600,
                                fontFamily: 'Inter',
                                height: 1.0,
                              ),
                            ),
                            SizedBox(width: dp(context, 4)),
                            SvgPicture.asset(
                              'assets/arrow_drop_down.svg',
                              width: dp(context, 24),
                              height: dp(context, 24),
                              colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        );

        final list = CustomScrollView(
          slivers: [
            if (groups.isEmpty) ...[
              SliverToBoxAdapter(
                child: Padding(
                  padding: EdgeInsets.only(top: dp(context, 24)),
                  child: Center(
                    child: Text(
                      'Нет записей за выбранный период',
                      style: TextStyle(
                        fontFamily: 'Inter',
                        fontSize: sp(context, 16),
                        fontWeight: FontWeight.w500,
                        color: isDark ? const Color(0xFFCCCCCC) : const Color(0xFF325674),
                        height: 1.0,
                      ),
                    ),
                  ),
                ),
              ),
              SliverToBoxAdapter(child: SizedBox(height: dp(context, 24))),
            ] else ...[
              for (final g in groups) ...[
                SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.only(right: side, top: dp(context, 4), bottom: dp(context, 4)),
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: Text(
                        _formatDate(g.key),
                        textAlign: TextAlign.right,
                        style: TextStyle(
                          color: dateColor,
                          fontSize: sp(context, 16),
                          fontWeight: FontWeight.w600,
                          fontFamily: 'Inter',
                          height: 1.0,
                        ),
                      ),
                    ),
                  ),
                ),
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                        (context, i) {
                      final r = g.value[i];
                      return Padding(
                        padding: EdgeInsets.fromLTRB(side, dp(context, 16), side, 0),
                        child: RecordListItem(
                          record: r,
                          onTap: () => _openEdit(context, r),
                        ),
                      );
                    },
                    childCount: g.value.length,
                  ),
                ),
                SliverToBoxAdapter(child: SizedBox(height: dp(context, 12))),
              ],
            ],
          ],
        );

        return ColoredBox(
          color: bg,
          child: Column(
            children: [
              SizedBox(
                height: blueH + lightH,
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    header,
                    Positioned(
                      left: side,
                      top: blueH - overlap,
                      child: SummaryCard(record: lastRecord),
                    ),
                  ],
                ),
              ),
              Expanded(child: list),
            ],
          ),
        );
      },
    );
  }

  List<MapEntry<DateTime, List<BloodPressureRecord>>> _groupByDate(List<BloodPressureRecord> records) {
    final grouped = <DateTime, List<BloodPressureRecord>>{};
    for (final r in records) {
      final d = DateTime(r.dateTime.year, r.dateTime.month, r.dateTime.day);
      grouped.putIfAbsent(d, () => []).add(r);
    }
    final keys = grouped.keys.toList()..sort((a, b) => b.compareTo(a));
    return [for (final k in keys) MapEntry(k, grouped[k]!)];
  }

  String _formatDate(DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);

    if (date == today) {
      return '${AppStrings.today}, ${DateFormat('d MMMM', 'ru').format(date)}';
    }
    return DateFormat('d MMMM yyyy, EEEE', 'ru').format(date);
  }
}
