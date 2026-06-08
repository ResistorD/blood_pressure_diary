import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/theme/scale.dart';
import '../../../../core/di/service_locator.dart';
import '../../../../core/repositories/pressure_repository.dart';
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

enum _FilterPeriod { today, week, month, all, custom }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  _FilterPeriod _period = _FilterPeriod.week;
  DateTimeRange? _customRange;
  final TextEditingController _searchController = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

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
      case _FilterPeriod.custom:
        final range = _customRange;
        if (range == null) return records;
        final start = DateTime(range.start.year, range.start.month, range.start.day);
        final end = DateTime(range.end.year, range.end.month, range.end.day, 23, 59, 59, 999);
        return records.where((r) => !r.dateTime.isBefore(start) && !r.dateTime.isAfter(end)).toList();
    }
  }

  List<BloodPressureRecord> _applySearch(
    BuildContext context,
    List<BloodPressureRecord> records,
  ) {
    final q = _query.trim().toLowerCase();
    if (q.isEmpty) return records;

    final locale = Localizations.localeOf(context).toString();
    final fmtFull = DateFormat('dd.MM.yyyy', locale);
    final fmtShort = DateFormat('dd.MM', locale);
    final fmtWords = DateFormat('d MMM yyyy', locale);
    final fmtTime = DateFormat('HH:mm', locale);

    return records.where((r) {
      final note = (r.note ?? '').toLowerCase();
      final tags = r.tags.join(' ').toLowerCase();
      final d = r.dateTime;
      final dateText = '${fmtFull.format(d)} ${fmtShort.format(d)} ${fmtWords.format(d)} ${fmtTime.format(d)}'
          .toLowerCase();
      return note.contains(q) || tags.contains(q) || dateText.contains(q);
    }).toList();
  }

  void _openEdit(BuildContext context, BloodPressureRecord record) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => AddRecordScreen(record: record)));
  }

  void _openAdd(BuildContext context) {
    Navigator.push(context, MaterialPageRoute(builder: (_) => const AddRecordScreen()));
  }

  Future<void> _handlePeriodChanged(BuildContext context, _FilterPeriod value) async {
    if (value == _FilterPeriod.custom) {
      final now = DateTime.now();
      final picked = await showDateRangePicker(
        context: context,
        firstDate: DateTime(now.year - 5, 1, 1),
        lastDate: DateTime(now.year + 1, 12, 31),
        initialDateRange: _customRange,
        helpText: _tr(context, ru: 'Выберите диапазон', en: 'Select range'),
      );
      if (picked == null || !mounted) return;
      setState(() {
        _period = value;
        _customRange = picked;
      });
      return;
    }
    setState(() {
      _period = value;
      _customRange = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;

    return BlocBuilder<HomeBloc, HomeState>(
      builder: (context, state) {
        final all = state is HomeLoaded ? state.records : const <BloodPressureRecord>[];
        final filtered = _applyFilter(all);
        final records = _applySearch(context, filtered)..sort((a, b) => b.dateTime.compareTo(a.dateTime));
        final filteredCount = records.length;

        final lastRecord = all.isNotEmpty
            ? (List<BloodPressureRecord>.from(all)..sort((a, b) => b.dateTime.compareTo(a.dateTime))).first
            : null;

        int? trendDelta;
        if (lastRecord != null && filtered.isNotEmpty) {
          final avgSys = filtered.map((r) => r.systolic).reduce((a, b) => a + b) / filtered.length;
          trendDelta = (lastRecord.systolic - avgSys).round();
        }

        return ColoredBox(
          color: colors.background,
          child: Column(
            children: [
              // ✅ Изолированный header (пересоздается только при изменении _period или filteredCount)
              _HomeHeader(
                period: _period,
                filteredCount: filteredCount,
                customRange: _customRange,
                onPeriodChanged: (value) => _handlePeriodChanged(context, value),
                lastRecord: lastRecord,
                trendDelta: trendDelta,
              ),
              // ✅ Изолированный список (пересоздается только при изменении records)
              Expanded(
                child: _RecordsList(
                  records: records,
                  onRecordTap: _openEdit,
                  onAddTap: () => _openAdd(context),
                  searchController: _searchController,
                  onQueryChanged: (v) => setState(() => _query = v),
                  hasQuery: _query.trim().isNotEmpty,
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
  final DateTimeRange? customRange;
  final int? trendDelta;

  const _HomeHeader({
    required this.period,
    required this.filteredCount,
    required this.onPeriodChanged,
    required this.lastRecord,
    required this.customRange,
    required this.trendDelta,
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
      case _FilterPeriod.custom:
        final range = customRange;
        if (range == null) return _tr(context, ru: 'Диапазон', en: 'Range');
        final locale = Localizations.localeOf(context).toString();
        final from = DateFormat('d MMM', locale).format(range.start);
        final to = DateFormat('d MMM', locale).format(range.end);
        return '$from–$to';
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
    // Ограничиваем вклад safeTop, чтобы устройства с "жирным" статус-баром
    // не уводили заголовок слишком низко.
    final cappedSafeTop = math.min(safeTop, dp(context, space.s24));
    final headerTop = cappedSafeTop + dp(context, space.s20);

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

    final summaryTop = blueH - overlap + dp(context, space.s4);

    double _textH(String s, TextStyle st) {
      final tp = TextPainter(
        text: TextSpan(text: s, style: st),
        textDirection: Directionality.of(context),
        maxLines: 1,
      )..layout(maxWidth: MediaQuery.of(context).size.width);
      return tp.height;
    }

    final titleH = _textH(_tr(context, ru: 'Мой дневник', en: 'My diary'), titleStyle);
    final countText = '$filteredCount ${_recordsWord(context, filteredCount)}';
    final countH = _textH(countText, countStyle);

    final safety = dp(context, space.s6);

    final maxGap = math.max(
      0.0,
      summaryTop - headerTop - titleH - countH - safety,
    );

    final minGap = dp(context, space.s8);
    final titleToCountGap = math.max(minGap, math.min(dp(context, space.s20), maxGap));

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
                      SizedBox(height: titleToCountGap),
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
                    PopupMenuItem(value: _FilterPeriod.custom, child: Text(_tr(context, ru: 'Диапазон дат', en: 'Date range'))),
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
            child: SummaryCard(record: lastRecord, trendDelta: trendDelta),
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
  final VoidCallback onAddTap;
  final TextEditingController searchController;
  final ValueChanged<String> onQueryChanged;
  final bool hasQuery;

  const _RecordsList({
    required this.records,
    required this.onRecordTap,
    required this.onAddTap,
    required this.searchController,
    required this.onQueryChanged,
    required this.hasQuery,
  });

  double _bottomInset(BuildContext context) {
    final space = context.appSpace;
    final safeBottom = MediaQuery.paddingOf(context).bottom;

    final barH = dp(context, space.s72 - space.s2 - space.s1);
    final outer = dp(context, space.s80 + space.s6);
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
    final radii = context.appRadii;
    final shadows = context.appShadow;
    final text = context.appText;

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

    final searchBg = colors.surface;
    final searchTextStyle = TextStyle(
      fontFamily: text.family,
      fontSize: sp(context, text.fs16),
      fontWeight: text.w500,
      color: colors.textPrimary,
      height: 1.0,
    );

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => FocusScope.of(context).unfocus(),
      child: CustomScrollView(
        slivers: [
        SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.fromLTRB(side, dp(context, space.s12), side, dp(context, space.s8)),
            child: Container(
              height: dp(context, space.s40 + space.s4),
              decoration: BoxDecoration(
                color: searchBg,
                borderRadius: BorderRadius.circular(dp(context, radii.r10)),
                boxShadow: [shadows.card],
              ),
              padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
              child: Row(
                children: [
                  Icon(Icons.search, size: dp(context, space.s20), color: colors.iconPrimary),
                  SizedBox(width: dp(context, space.s8)),
                  Expanded(
                    child: TextField(
                      controller: searchController,
                      onChanged: onQueryChanged,
                      decoration: InputDecoration(
                        border: InputBorder.none,
                        isCollapsed: true,
                        hintText: _tr(context, ru: 'Поиск по дате, заметке, тегам', en: 'Search by date, note, tags'),
                        hintStyle: searchTextStyle.copyWith(color: colors.textSecondary),
                      ),
                      style: searchTextStyle,
                    ),
                  ),
                  if (hasQuery)
                    GestureDetector(
                      onTap: () {
                        searchController.clear();
                        onQueryChanged('');
                      },
                      child: Icon(Icons.close, size: dp(context, space.s20), color: colors.iconPrimary),
                    ),
                ],
              ),
            ),
          ),
        ),
        if (groups.isEmpty) ...[
          SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.only(top: dp(context, space.s24)),
              child: Center(
                child: Column(
                  children: [
                    SvgPicture.asset(
                      'assets/pill.svg',
                      width: dp(context, space.s72),
                      height: dp(context, space.s72),
                      colorFilter: ColorFilter.mode(colors.textPrimary, BlendMode.srcIn),
                    ),
                    SizedBox(height: dp(context, space.s12)),
                    Text(
                      hasQuery
                          ? _tr(context, ru: 'Ничего не найдено', en: 'No results found')
                          : _tr(context, ru: 'Пока нет записей', en: 'No records yet'),
                      style: emptyStyle,
                      textAlign: TextAlign.center,
                    ),
                    SizedBox(height: dp(context, space.s8)),
                    Text(
                      _tr(context, ru: 'Добавьте первое измерение', en: 'Add your first measurement'),
                      style: emptyStyle.copyWith(
                        fontSize: sp(context, context.appText.fs14),
                        fontWeight: context.appText.w500,
                        color: colors.textSecondary,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    SizedBox(height: dp(context, space.s16)),
                    SizedBox(
                      height: dp(context, space.s40 + space.s4),
                      child: ElevatedButton(
                        onPressed: onAddTap,
                        style: ElevatedButton.styleFrom(
                          elevation: 0,
                          backgroundColor: colors.brandStrong,
                          foregroundColor: colors.textOnBrand,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(dp(context, radii.r10)),
                          ),
                        ),
                        child: Text(
                          _tr(context, ru: 'Добавить запись', en: 'Add record'),
                          style: TextStyle(
                            fontFamily: context.appText.family,
                            fontSize: sp(context, context.appText.fs16),
                            fontWeight: context.appText.w600,
                            height: 1.0,
                          ),
                        ),
                      ),
                    ),
                  ],
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
                    child: _DismissibleRecord(
                      record: r,
                      child: RecordListItem(
                        record: r,
                        onTap: () => onRecordTap(context, r),
                      ),
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
      ),
    );
  }
}

class _DismissibleRecord extends StatelessWidget {
  final BloodPressureRecord record;
  final Widget child;

  const _DismissibleRecord({
    required this.record,
    required this.child,
  });

  Future<void> _deleteWithUndo(BuildContext context) async {
    final repo = getIt<PressureRepository>();
    await repo.deleteRecord(record.id);
    if (!context.mounted) return;

    final messenger = ScaffoldMessenger.of(context);
    messenger.hideCurrentSnackBar();
    messenger.showSnackBar(
      SnackBar(
        content: Text(_tr(context, ru: 'Запись удалена', en: 'Record deleted')),
        action: SnackBarAction(
          label: _tr(context, ru: 'Отменить', en: 'Undo'),
          onPressed: () {
            repo.addRecord(record);
          },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;

    final bg = colors.danger;
    final iconSize = dp(context, space.s20);

    return Dismissible(
      key: ValueKey(record.id),
      direction: DismissDirection.endToStart,
      onDismissed: (_) => _deleteWithUndo(context),
      background: const SizedBox.shrink(),
      secondaryBackground: Container(
        alignment: Alignment.centerRight,
        padding: EdgeInsets.symmetric(horizontal: dp(context, space.s16)),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(dp(context, radii.r10)),
        ),
        child: Icon(Icons.delete_outline, color: colors.textOnBrand, size: iconSize),
      ),
      child: child,
    );
  }
}
