import 'dart:io';
import 'package:csv/csv.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart' show rootBundle, Uint8List;
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:share_plus/share_plus.dart';

import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';

enum ExportFormat { csv, pdf }

class ExportService {
  // ✅ Кэш для шрифтов PDF
  pw.Font? _cachedTtf;
  pw.Font? _cachedTtfBold;
  
  Future<pw.Font> _loadTtf() async {
    if (_cachedTtf != null) return _cachedTtf!;
    final fontData = await rootBundle.load('assets/fonts/Inter-Regular.ttf');
    _cachedTtf = pw.Font.ttf(fontData);
    return _cachedTtf!;
  }

  Future<pw.Font> _loadTtfBold() async {
    if (_cachedTtfBold != null) return _cachedTtfBold!;
    final boldData = await rootBundle.load('assets/fonts/Inter-Bold.ttf');
    _cachedTtfBold = pw.Font.ttf(boldData);
    return _cachedTtfBold!;
  }

  Future<void> exportData(
      List<BloodPressureRecord> records,
      ExportFormat format,
      String languageCode, {
        UserProfile? profile,
        int periodDays = 14,
      }) async {
    if (format == ExportFormat.csv) {
      await _exportToCSV(records);
      return;
    }

    await _exportToPDFDoctorReport(
      records: records,
      languageCode: languageCode,
      profile: profile,
      periodDays: periodDays,
    );
  }

  // --- ВОССТАНОВЛЕННЫЙ CSV ---
  Future<void> _exportToCSV(List<BloodPressureRecord> records) async {
    List<List<dynamic>> rows = [
      ["Date", "Time", "Systolic", "Diastolic", "Pulse", "Note"]
    ];

    for (var record in records) {
      rows.add([
        DateFormat('dd.MM.yyyy').format(record.dateTime),
        DateFormat('HH:mm').format(record.dateTime),
        record.systolic,
        record.diastolic,
        record.pulse,
        record.note ?? ""
      ]);
    }

    String csv = const ListToCsvConverter().convert(rows);
    final dir = await getTemporaryDirectory();
    final file = File(
      '${dir.path}/blood_pressure_export_${DateTime.now().millisecondsSinceEpoch}.csv',
    );

    await file.writeAsBytes(Uint8List.fromList(csv.codeUnits));
    await Share.shareXFiles([XFile(file.path)]);
  }

  // --- PDF (Doctor report) ---
  Future<void> _exportToPDFDoctorReport({
    required List<BloodPressureRecord> records,
    required String languageCode,
    UserProfile? profile,
    int periodDays = 14,
  }) async {
    final bool isRu = languageCode == 'ru';
    final primaryColor = PdfColor.fromHex('#2E5D85');
    final lightGrey = PdfColors.grey100;

    final now = DateTime.now();
    final threshold = now.subtract(Duration(days: periodDays));
    final filtered = records.where((r) => r.dateTime.isAfter(threshold)).toList();

    // ✅ Использование кэшированных шрифтов
    final ttf = await _loadTtf();
    final ttfBold = await _loadTtfBold();

    final ageYears = _tryGetAgeYears(profile, now);
    final ageStr = ageYears != null ? ageYears.toString() : '—';

    final periodStr =
        '${DateFormat('dd.MM.yyyy').format(threshold)} – ${DateFormat('dd.MM.yyyy').format(now)}';

    final pdf = pw.Document();
    final stats = _calculateStats(filtered, profile);

    pdf.addPage(
      pw.MultiPage(
        theme: pw.ThemeData.withFont(base: ttf, bold: ttfBold),
        margin: const pw.EdgeInsets.all(35),
        build: (context) => [
          pw.Text(
            isRu ? 'Отчёт по артериальному давлению' : 'Blood Pressure Report',
            style: pw.TextStyle(
              font: ttfBold,
              fontSize: 18,
              color: primaryColor,
            ),
          ),
          pw.SizedBox(height: 12),

          pw.Text('${isRu ? 'Период' : 'Period'}: $periodStr',
              style: const pw.TextStyle(fontSize: 10)),
          pw.Text('${isRu ? 'Пациент' : 'Patient'}: ${_profileName(profile)}',
              style: const pw.TextStyle(fontSize: 10)),
          pw.Text('${isRu ? 'Возраст' : 'Age'}: $ageStr',
              style: const pw.TextStyle(fontSize: 10)),
          pw.Text(
            '${isRu ? 'Целевые значения' : 'Target values'}: ${profile?.targetSystolic ?? 120}/${profile?.targetDiastolic ?? 80}',
            style: const pw.TextStyle(fontSize: 10),
          ),

          pw.SizedBox(height: 20),

          // 1. РЕЗЮМЕ
          _buildTitle(isRu ? 'Резюме' : 'Summary', primaryColor),
          _buildResumeTable(
            rows: [
              [isRu ? 'Среднее за период' : 'Average', '${stats.avgSys}/${stats.avgDia}'],
              [isRu ? 'Минимум' : 'Minimum', '${stats.minSys}/${stats.minDia}'],
              [isRu ? 'Максимум' : 'Maximum', '${stats.maxSys}/${stats.maxDia}'],
              [
                isRu ? 'Выше нормы' : 'Above normal',
                '${stats.outOfRangePct.round()}% (${stats.outOfRangeCount}/${stats.n})'
              ],
            ],
            bgColor: lightGrey,
          ),

          pw.SizedBox(height: 10),

          // 2. АНАЛИТИКА
          _buildTitle(isRu ? 'Аналитика по времени суток' : 'Time of day analytics', primaryColor),
          _buildStandardTable(
            headers: [
              isRu ? 'Время суток' : 'Time of day',
              isRu ? 'Среднее (SYS/DIA)' : 'Avg (SYS/DIA)'
            ],
            rows: _calcTimeBuckets(filtered, isRu),
            headerColor: primaryColor,
          ),

          pw.SizedBox(height: 10),

          // 3. ЖУРНАЛ
          _buildTitle(isRu ? 'Журнал измерений' : 'Measurement log', primaryColor),
          _buildStandardTable(
            headers: isRu
                ? ['Дата', 'Время', 'SYS/DIA', 'Пульс', 'Примечание']
                : ['Date', 'Time', 'SYS/DIA', 'Pulse', 'Note'],
            rows: filtered
                .map((r) => [
              DateFormat('dd.MM.yyyy').format(r.dateTime),
              DateFormat('HH:mm').format(r.dateTime),
              '${r.systolic}/${r.diastolic}',
              r.pulse.toString(),
              _noteWithTags(r), // ✅ note + tags
            ])
                .toList(),
            headerColor: primaryColor,
            isJournal: true,
          ),

          pw.SizedBox(height: 20),

          // 4. ЗАМЕТКИ ВРАЧА
          pw.Text(isRu ? 'Заметки врача:' : 'Doctor\'s notes:',
              style: pw.TextStyle(font: ttfBold, fontSize: 10)),
          pw.SizedBox(height: 5),
          pw.Column(
            children: List.generate(
              7,
                  (index) => pw.Container(
                height: 18,
                decoration: const pw.BoxDecoration(
                  border: pw.Border(
                    bottom: pw.BorderSide(color: PdfColors.black, width: 0.5),
                  ),
                ),
              ),
            ),
          ),
          pw.SizedBox(height: 20),
          pw.Text(
            isRu
                ? 'Данные внесены пользователем и не являются медицинским измерением. Интерпретация требует клинической верификации.'
                : 'Data entered by user. Requires clinical verification.',
            style: pw.TextStyle(font: ttf, fontSize: 8, color: PdfColors.black),
          ),
        ],
      ),
    );

    final bytes = await pdf.save();
    
    // ✅ Использование постоянного хранилища вместо temporary
    final dir = await getApplicationDocumentsDirectory();
    final exportDir = Directory('${dir.path}/exports');
    
    // Создаем директорию, если её нет
    if (!await exportDir.exists()) {
      await exportDir.create(recursive: true);
    }
    
    // ✅ Cleanup файлов старше 7 дней
    try {
      await for (final entity in exportDir.list()) {
        if (entity is File) {
          final stat = await entity.stat();
          if (now.difference(stat.modified).inDays > 7) {
            await entity.delete();
          }
        }
      }
    } catch (e) {
      // Ignore cleanup errors
      debugPrint('Cleanup old exports error: $e');
    }
    
    final file = File('${exportDir.path}/report_${now.millisecondsSinceEpoch}.pdf');
    await file.writeAsBytes(bytes, flush: true);
    await Share.shareXFiles([XFile(file.path)]);
  }

  // ✅ ЕДИНСТВЕННОЕ целевое добавление: теги попадают в "Примечание" в PDF
  String _noteWithTags(BloodPressureRecord r) {
    final note = (r.note ?? '').trim();
    final tags = r.tags; // List<String>, по модели не nullable

    final tagText = tags.join(', ').trim();
    if (tagText.isEmpty) return note;

    if (note.isEmpty) return tagText;

    return '$note\n$tagText';
  }

  pw.Widget _buildTitle(String text, PdfColor color) => pw.Padding(
    padding: const pw.EdgeInsets.only(bottom: 6),
    child: pw.Text(
      text,
      style: pw.TextStyle(
        fontSize: 12,
        fontWeight: pw.FontWeight.bold,
        color: color,
      ),
    ),
  );

  pw.Widget _buildResumeTable({required List<List<String>> rows, required PdfColor bgColor}) {
    return pw.Container(
      decoration: pw.BoxDecoration(
        color: bgColor,
        borderRadius: pw.BorderRadius.circular(8),
      ),
      child: pw.ClipRRect(
        horizontalRadius: 8,
        verticalRadius: 8,
        child: pw.TableHelper.fromTextArray(
          border: null,
          cellStyle: const pw.TextStyle(fontSize: 9),
          data: rows,
          columnWidths: {0: const pw.FixedColumnWidth(150), 1: const pw.FlexColumnWidth()},
          cellAlignments: {0: pw.Alignment.centerLeft, 1: pw.Alignment.center},
          cellPadding: const pw.EdgeInsets.symmetric(horizontal: 10, vertical: 5),
        ),
      ),
    );
  }

  pw.Widget _buildStandardTable({
    List<String>? headers,
    required List<List<String>> rows,
    required PdfColor headerColor,
    bool isJournal = false,
  }) {
    return pw.Container(
      decoration: pw.BoxDecoration(
        border: pw.Border.all(color: PdfColors.black, width: 0.8),
        borderRadius: pw.BorderRadius.circular(8),
      ),
      child: pw.ClipRRect(
        horizontalRadius: 8,
        verticalRadius: 8,
        child: pw.TableHelper.fromTextArray(
          border: const pw.TableBorder(
            horizontalInside: pw.BorderSide(color: PdfColors.black, width: 0.5),
            verticalInside: pw.BorderSide(color: PdfColors.black, width: 0.5),
          ),
          headerStyle: pw.TextStyle(
            color: PdfColors.white,
            fontSize: 9,
            fontWeight: pw.FontWeight.bold,
          ),
          headerDecoration: pw.BoxDecoration(color: headerColor),
          cellStyle: const pw.TextStyle(fontSize: 9),
          cellAlignment: pw.Alignment.center,
          headers: headers,
          data: rows,
          columnWidths: isJournal
              ? {
            0: const pw.FixedColumnWidth(65),
            1: const pw.FixedColumnWidth(45),
            2: const pw.FixedColumnWidth(60),
            3: const pw.FixedColumnWidth(45),
            4: const pw.FlexColumnWidth(),
          }
              : {0: const pw.FixedColumnWidth(215), 1: const pw.FlexColumnWidth()},
          cellPadding: const pw.EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        ),
      ),
    );
  }

  String _profileName(UserProfile? p) {
    final name = (p?.name ?? '').trim();
    return name.isEmpty ? '—' : name;
  }

  DateTime? _tryParseDob(UserProfile? p) {
    if (p == null || p.age == 0) return null;
    final s = p.age.toString();
    if (s.length != 8) return null;
    return DateTime(
      int.parse(s.substring(0, 4)),
      int.parse(s.substring(4, 6)),
      int.parse(s.substring(6, 8)),
    );
  }

  int? _tryGetAgeYears(UserProfile? p, DateTime now) {
    if (p == null) return null;
    final v = p.age;
    if (v == 0) return null;

    final s = v.toString();
    if (s.length == 8) {
      final dob = _tryParseDob(p);
      if (dob == null) return null;
      int years = now.year - dob.year;
      final hadBirthdayThisYear =
          (now.month > dob.month) || (now.month == dob.month && now.day >= dob.day);
      if (!hadBirthdayThisYear) years -= 1;
      return years;
    }

    // иначе считаем, что age хранится как "возраст в годах"
    return v;
  }

  _Stats _calculateStats(List<BloodPressureRecord> records, UserProfile? profile) {
    if (records.isEmpty) return _Stats.empty();
    int sSum = 0, dSum = 0, outCount = 0;
    int minS = 999, maxS = 0, minD = 999, maxD = 0;
    final tS = profile?.targetSystolic ?? 140;
    final tD = profile?.targetDiastolic ?? 90;
    for (var r in records) {
      sSum += r.systolic;
      dSum += r.diastolic;
      if (r.systolic < minS) minS = r.systolic;
      if (r.systolic > maxS) maxS = r.systolic;
      if (r.diastolic < minD) minD = r.diastolic;
      if (r.diastolic > maxD) maxD = r.diastolic;
      if (r.systolic > tS || r.diastolic > tD) outCount++;
    }
    return _Stats(
      n: records.length,
      avgSys: (sSum / records.length).round(),
      avgDia: (dSum / records.length).round(),
      minSys: minS,
      maxSys: maxS,
      minDia: minD,
      maxDia: maxD,
      outOfRangeCount: outCount,
      outOfRangePct: (outCount / records.length) * 100,
    );
  }

  List<List<String>> _calcTimeBuckets(List<BloodPressureRecord> records, bool isRu) {
    final b = {
      'm': <BloodPressureRecord>[],
      'd': <BloodPressureRecord>[],
      'e': <BloodPressureRecord>[],
      'n': <BloodPressureRecord>[],
    };
    for (var r in records) {
      final h = r.dateTime.hour;
      if (h >= 6 && h < 11) b['m']!.add(r);
      else if (h >= 11 && h < 18) b['d']!.add(r);
      else if (h >= 18 && h < 23) b['e']!.add(r);
      else if (h >= 23 || h < 6) b['n']!.add(r);
    }
    String f(List<BloodPressureRecord> l) {
      if (l.isEmpty) return '—';
      final s =
      (l.map((e) => e.systolic).reduce((a, b) => a + b) / l.length).round();
      final d =
      (l.map((e) => e.diastolic).reduce((a, b) => a + b) / l.length).round();
      final label = isRu
          ? (l.length == 1
          ? 'измерение'
          : (l.length < 5 ? 'измерения' : 'измерений'))
          : 'records';
      return '$s/$d (${l.length} $label)';
    }
    return [
      [isRu ? 'Утро (06-11)' : 'Morning', f(b['m']!)],
      [isRu ? 'День (11-18)' : 'Day', f(b['d']!)],
      [isRu ? 'Вечер (18-23)' : 'Evening', f(b['e']!)],
      [isRu ? 'Ночь (23-06)' : 'Night', f(b['n']!)],
    ];
  }
}

class _Stats {
  final int n, avgSys, avgDia, minSys, maxSys, minDia, maxDia, outOfRangeCount;
  final double outOfRangePct;
  _Stats({
    required this.n,
    required this.avgSys,
    required this.avgDia,
    required this.minSys,
    required this.maxSys,
    required this.minDia,
    required this.maxDia,
    required this.outOfRangeCount,
    required this.outOfRangePct,
  });
  static _Stats empty() => _Stats(
    n: 0,
    avgSys: 0,
    avgDia: 0,
    minSys: 0,
    maxSys: 0,
    minDia: 0,
    maxDia: 0,
    outOfRangeCount: 0,
    outOfRangePct: 0,
  );
}
