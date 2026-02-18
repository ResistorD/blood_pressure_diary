import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/theme/scale.dart';
import '../data/blood_pressure_model.dart';
import 'bloc/home_bloc.dart';
import 'bloc/home_state.dart';
import 'widgets/summary_card.dart';
import 'widgets/record_list_item.dart';
import '../../add_record/presentation/add_record_screen.dart';

String _tr(BuildContext context, {required String ru, required String en}) {
  final code = Localizations.localeOf(context).languageCode.toLowerCase();
  return code == 'ru' ? ru : en;
}

String _recordsWord(BuildContext context, int n) {
  if (Localizations.localeOf(context).languageCode.toLowerCase() != 'ru') {
    return n == 1 ? 'record' : 'records';
  }
  if (n % 10 == 1 && n % 100 != 11) return 'запись';
  if ([2, 3, 4].contains(n % 10) && ![12, 13, 14].contains(n % 100)) return 'записи';
  return 'записей';
}

enum _FilterPeriod { today, week, month, all }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  _FilterPeriod _period = _FilterPeriod.week;

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
    final colors = context.appColors;

    return BlocBuilder<HomeBloc, HomeState>(
      builder: (context, state) {
        final all = state is HomeLoaded ? state.records : const <BloodPressureRecord>[];
        final records = _applyFilter(all)..sort((a, b) => b.dateTime.compareTo(a.dateTime));
        final filteredCount = records.length;

        final lastRecord = all.isNotEmpty
            ? (List<BloodPressureRecord>.from(all)..sort((a, b) => b.dateTime.compareTo(a.dateTime))).first
            : null;

        return ColoredBox(
          color: colors.background,
          child: Column(
            children: [
              // ✅ Изолированный header (пересоздается только при изменении _period или filteredCount)
              _HomeHeader(
                period: _period,
                filteredCount: filteredCount,
                onPeriodChanged: (value) => setState(() => _period = value),
                lastRecord: lastRecord,
              ),
              // ✅ Изолированный список (пересоздается только при изменении records)
              Expanded(
                child: _RecordsList(
                  records: records,
                  onRecordTap: _openEdit,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// ✅ Изолированный виджет header
class _HomeHeader extends StatelessWidget {
  final _FilterPeriod period;
  final int filteredCount;
  final ValueChanged<_FilterPeriod> onPeriodChanged;
  final BloodPressureRecord? lastRecord;

  const _HomeHeader({
    required this.period,
    required this.filteredCount,
    required this.onPeriodChanged,
    required this.lastRecord,
  });

  String _periodLabel(BuildContext context, _FilterPeriod p) {
    switch (p) {
      case _FilterPeriod.today:
        return _tr(context, ru: 'Сегодня', en: 'Today');
      case _FilterPeriod.week:
        return _tr(context, ru: 'Неделя', en: 'Week');
      case _FilterPeriod.month:
        return _tr(context, ru: 'Месяц', en: 'Month');
      case _FilterPeriod.all:
        return _tr(context, ru: 'Все', en: 'All');
    }
  }

  @override
  Widget build(BuildContext context) {
    final safeTop = MediaQuery.of(context).padding.top;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final appText = context.appText;

    final side = HeaderSizes.horizontalPadding(context);
    final blueH = HeaderSizes.blueHeight(context);
    final shelfH = HeaderSizes.shelfHeight(context);
    final overlap = HeaderSizes.overlap(context);
    final headerTop = safeTop + context.adaptiveVerticalPadding;

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final shelfBg = isDark ? AppPalette.dark700 : AppPalette.grey050;

    final dividerH = dp(context, space.s1) / dp(context, space.s2);
    final shelfDivider = isDark ? Colors.transparent : colors.divider;

    final shelfShadow = BoxShadow(
      offset: Offset(0, dp(context, space.s1)),
      blurRadius: dp(context, space.s4),
      color: colors.shadow,
    );

    final chipH = dp(context, space.s32);
    final chipR = dp(context, radii.r5);
    final chipHPad = dp(context, space.s10);
    final chipGap = dp(context, space.s4);
    final icon24 = dp(context, space.s24);

    final chipBg = isDark ? AppPalette.dark700 : AppPalette.blue500;
    final chipText = colors.textOnBrand;

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

    return SizedBox(
      height: blueH + shelfH,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          // Background
          Positioned.fill(child: ColoredBox(color: headerBg)),
          // Shelf
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
          // Title and filter
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
                        _tr(context, ru: 'Мой дневник', en: 'My diary'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: titleStyle,
                      ),
                      SizedBox(height: dp(context, space.s20)),
                      Text(
                        '$filteredCount ${_recordsWord(context, filteredCount)}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: countStyle,
                      ),
                    ],
                  ),
                ),
                PopupMenuButton<_FilterPeriod>(
                  onSelected: onPeriodChanged,
                  itemBuilder: (context) => [
                    PopupMenuItem(value: _FilterPeriod.today, child: Text(_tr(context, ru: 'Сегодня', en: 'Today'))),
                    PopupMenuItem(value: _FilterPeriod.week, child: Text(_tr(context, ru: 'Неделя', en: 'Week'))),
                    PopupMenuItem(value: _FilterPeriod.month, child: Text(_tr(context, ru: 'Месяц', en: 'Month'))),
                    PopupMenuItem(value: _FilterPeriod.all, child: Text(_tr(context, ru: 'За всё время', en: 'All time'))),
                  ],
                  offset: Offset(0, dp(context, space.s30 - space.s2)),
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
                          _periodLabel(context, period),
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
          // Summary card
          Positioned(
            left: side,
            right: side,
            top: blueH - overlap + dp(context, space.s4),
            child: SummaryCard(record: lastRecord),
          ),
        ],
      ),
    );
  }
}

/// ✅ Изолированный виджет списка записей
class _RecordsList extends StatelessWidget {
  final List<BloodPressureRecord> records;
  final void Function(BuildContext, BloodPressureRecord) onRecordTap;

  const _RecordsList({
    required this.records,
    required this.onRecordTap,
  });

  double _bottomInset(BuildContext context) {
    final space = context.appSpace;
    final safeBottom = MediaQuery.paddingOf(context).bottom;

    final barH = dp(context, space.s72 - space.s2 - space.s1);
    final outer = dp(context, space.s80 + space.s6);
    final lift = outer / 2;

    return barH + safeBottom + dp(context, space.s8);
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

  String _formatDate(BuildContext context, DateTime date) {
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final locale = Localizations.localeOf(context).toString();

    if (date == today) {
      return '${_tr(context, ru: 'Сегодня', en: 'Today')}, ${DateFormat('d MMMM', locale).format(date)}';
    }

    return DateFormat('d MMMM yyyy, EEEE', locale).format(date);
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final space = context.appSpace;

    final side = HeaderSizes.horizontalPadding(context);
    final bottomListPadding = _bottomInset(context);

    final groups = _groupByDate(records);

    final dateStyle = TextStyle(
      fontFamily: context.appText.family,
      fontSize: sp(context, context.appText.fs16),
      fontWeight: context.appText.w600,
      color: colors.textPrimary,
      height: 1.0,
    );

    final emptyStyle = TextStyle(
      fontFamily: context.appText.family,
      fontSize: sp(context, context.appText.fs16),
      fontWeight: context.appText.w600,
      color: colors.textPrimary,
      height: 1.0,
    );

    return CustomScrollView(
      slivers: [
        if (groups.isEmpty) ...[
          SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.only(top: dp(context, space.s24)),
              child: Center(
                child: Text(
                  _tr(context, ru: 'Нет записей за выбранный период', en: 'No records for selected period'),
                  style: emptyStyle,
                ),
              ),
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
                  child: Text(_formatDate(context, entry.$2.key), textAlign: TextAlign.right, style: dateStyle),
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
                      onTap: () => onRecordTap(context, r),
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
  }
}
