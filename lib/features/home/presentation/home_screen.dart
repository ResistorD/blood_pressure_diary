import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/app_theme.dart';
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

  double _bottomInset(BuildContext context) {
    // Bottom bar in AppNavigation: barH (69) + lift (43) ≈ 112, плюс safeBottom.
    final space = context.appSpace;
    final safeBottom = MediaQuery.paddingOf(context).bottom;

    final barH = dp(context, space.s72 - space.s2 - space.s1);
    final outer = dp(context, space.s80 + space.s6);
    final lift = outer / 2;

    return barH + lift + safeBottom + dp(context, space.s12);
  }

  @override
  Widget build(BuildContext context) {
    final safeTop = MediaQuery.of(context).padding.top;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final appText = context.appText;

    // Layout tokens
    final side = dp(context, space.s20);
    final blueH = dp(context, space.s160); // header blue
    final shelfH = dp(context, space.s80); // shelf
    final overlap = dp(context, space.s40 + space.s10); // 50
    final headerTop = safeTop + dp(context, space.s20);

    // Header colors (точно как в макете главного экрана)
    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final shelfBg = isDark ? AppPalette.dark700 : AppPalette.grey050;

    // Divider 0.5px (через s1/s2)
    final dividerH = dp(context, space.s1) / dp(context, space.s2);
    final shelfDivider = isDark ? Colors.transparent : colors.divider;

    // Деликатная тень у полки: меньше blur/offset, чем “карточная”
    final shelfShadow = BoxShadow(
      offset: Offset(0, dp(context, space.s1)),
      blurRadius: dp(context, space.s4),
      color: colors.shadow,
    );

    // Chip
    final chipH = dp(context, space.s32);
    final chipR = dp(context, radii.r5);
    final chipHPad = dp(context, space.s10);
    final chipGap = dp(context, space.s4);
    final icon24 = dp(context, space.s24);

    final chipBg = isDark ? AppPalette.dark700 : AppPalette.blue500;
    final chipText = colors.textOnBrand;

    // Typography
    final titleStyle = TextStyle(
      fontFamily: appText.family,
      fontSize: sp(context, appText.fs26),
      fontWeight: appText.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final countStyle = TextStyle(
      fontFamily: appText.family,
      fontSize: sp(context, appText.fs16),
      fontWeight: appText.w500,
      color: isDark ? AppPalette.dark400 : AppPalette.blue300,
      height: 1.0,
    );

    final dateStyle = TextStyle(
      fontFamily: appText.family,
      fontSize: sp(context, appText.fs16),
      fontWeight: appText.w600,
      color: colors.textPrimary,
      height: 1.0,
    );

    final emptyStyle = TextStyle(
      fontFamily: appText.family,
      fontSize: sp(context, appText.fs16),
      fontWeight: appText.w600,
      color: colors.textPrimary,
      height: 1.0,
    );

    // ✅ Нижний “запас” под навбар + FAB + safeBottom (устойчиво на разных девайсах)
    final bottomListPadding = _bottomInset(context);

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
          height: blueH + shelfH,
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Positioned.fill(child: ColoredBox(color: headerBg)),
              Positioned(
                left: 0,
                right: 0,
                top: blueH,
                height: shelfH,
                child: Container(
                  decoration: BoxDecoration(
                    color: shelfBg,
                    boxShadow: [shelfShadow],
                  ),
                  child: Align(
                    alignment: Alignment.bottomCenter,
                    child: SizedBox(
                      height: dividerH,
                      child: ColoredBox(color: shelfDivider),
                    ),
                  ),
                ),
              ),
              Positioned(
                left: side,
                right: side,
                top: headerTop,
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
                            style: titleStyle,
                          ),
                          SizedBox(height: dp(context, space.s20)),
                          Text(
                            '$filteredCount ${_recordsWord(filteredCount)}',
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: countStyle,
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
                      offset: Offset(0, dp(context, space.s30 - space.s2)), // 28
                      child: Container(
                        height: chipH,
                        padding: EdgeInsets.symmetric(horizontal: chipHPad),
                        decoration: BoxDecoration(
                          color: chipBg,
                          borderRadius: BorderRadius.circular(chipR),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Text(
                              _periodLabel(_period),
                              style: TextStyle(
                                fontFamily: appText.family,
                                fontSize: sp(context, appText.fs16),
                                fontWeight: appText.w600,
                                color: chipText,
                                height: 1.0,
                              ),
                            ),
                            SizedBox(width: chipGap),
                            SvgPicture.asset(
                              'assets/arrow_drop_down.svg',
                              width: icon24,
                              height: icon24,
                              colorFilter: ColorFilter.mode(chipText, BlendMode.srcIn),
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
                  padding: EdgeInsets.only(top: dp(context, space.s24)),
                  child: Center(child: Text('Нет записей за выбранный период', style: emptyStyle)),
                ),
              ),
              SliverToBoxAdapter(child: SizedBox(height: bottomListPadding)),
            ] else ...[
              SliverToBoxAdapter(child: SizedBox(height: dp(context, space.s10))),
              for (final entry in groups.indexed) ...[
                SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.only(
                      right: side,
                      top: dp(context, space.s2),
                      bottom: dp(context, space.s2),
                    ),
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: Text(_formatDate(entry.$2.key), textAlign: TextAlign.right, style: dateStyle),
                    ),
                  ),
                ),
                SliverList(
                  delegate: SliverChildBuilderDelegate(
                        (context, i) {
                      final r = entry.$2.value[i];
                      return Padding(
                        padding: EdgeInsets.fromLTRB(side, dp(context, space.s12), side, 0),
                        child: RecordListItem(
                          record: r,
                          onTap: () => _openEdit(context, r),
                        ),
                      );
                    },
                    childCount: entry.$2.value.length,
                  ),
                ),
                SliverToBoxAdapter(child: SizedBox(height: dp(context, space.s10))),
              ],
              SliverToBoxAdapter(child: SizedBox(height: bottomListPadding)),
            ],
          ],
        );

        return ColoredBox(
          color: colors.background,
          child: Column(
            children: [
              SizedBox(
                height: blueH + shelfH,
                child: Stack(
                  clipBehavior: Clip.none,
                  children: [
                    header,
                    Positioned(
                      left: side,
                      right: side,
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
