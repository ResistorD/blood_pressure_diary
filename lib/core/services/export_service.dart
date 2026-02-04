// export_service.dart (полная замена — возраст + "5 измерений" + "Ночь (22–06)")
import 'dart:io';

import 'package:csv/csv.dart';
import 'package:flutter/services.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:share_plus/share_plus.dart';

import 'package:blood_pressure_diary/core/database/models/user_profile.dart';
import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';

enum ExportFormat { csv, pdf }

class ExportService {
  /// PDF: v1 “отчёт для врача” (без графиков).
  /// [profile] — имя/дата рождения (в profile.age)/нормы (targetSystolic/targetDiastolic).
  /// [periodDays] — период отчёта (3/14/30/90).
  Future<void> exportData(
      List<BloodPressureRecord> records,
      ExportFormat format,
      String languageCode, {
        UserProfile? profile,
        int periodDays = 14,
      }) async {
    if (format == ExportFormat.csv) {
      await _exportToCSV(records);
    } else {
      await _exportToPDFDoctorReport(
        records: records,
        languageCode: languageCode,
        profile: profile,
        periodDays: periodDays,
      );
    }
  }

  Future<void> _exportToCSV(List<BloodPressureRecord> records) async {
    final List<List<dynamic>> rows = [
      ['Date', 'Time', 'Systolic', 'Diastolic', 'Pulse', 'Note']
    ];

    for (final record in records) {
      rows.add([
        DateFormat('dd.MM.yyyy').format(record.dateTime),
        DateFormat('HH:mm').format(record.dateTime),
        record.systolic,
        record.diastolic,
        record.pulse,
        record.note ?? '',
      ]);
    }

    final csvContent = const ListToCsvConverter().convert(rows);
    final directory = await getTemporaryDirectory();
    final file = File('${directory.path}/blood_pressure_export.csv');
    await file.writeAsString(csvContent);

    await Share.shareXFiles([XFile(file.path)], text: 'Blood Pressure Export (CSV)');
  }

  // --------------------- PDF v1 (Doctor report, no charts) ---------------------

  // Диапазоны (как в отчёте):
  // Утро: 06–10  => [06:00, 11:00)
  // День: 12–16  => [12:00, 17:00)
  // Вечер: 18–22 => [18:00, 22:00)
  // Ночь: 22–06  => всё остальное
  static const _kMorningStart = 6 * 60;
  static const _kMorningEnd = 11 * 60;

  static const _kDayStart = 12 * 60;
  static const _kDayEnd = 17 * 60;

  static const _kEveningStart = 18 * 60;
  static const _kEveningEnd = 22 * 60;

  int _toMinutes(DateTime dt) => dt.hour * 60 + dt.minute;

  String _fmtDate(DateTime dt) => DateFormat('dd.MM.yyyy').format(dt);
  String _fmtTime(DateTime dt) => DateFormat('HH:mm').format(dt);

  int? _computeAge(UserProfile? profile) {
    final dob = _tryParseDobFromProfile(profile);
    if (dob == null) return null;

    final now = DateTime.now();
    var age = now.year - dob.year;
    final hadBirthday = (now.month > dob.month) || (now.month == dob.month && now.day >= dob.day);
    if (!hadBirthday) age--;
    if (age < 0 || age > 130) return null;
    return age;
  }

  DateTime? _tryParseDobFromProfile(UserProfile? profile) {
    if (profile == null) return null;

    final v = profile.age;

    // 1) возраст в годах
    if (v > 0 && v <= 130) {
      // точной даты нет — но возраст показать можно
      return DateTime(DateTime.now().year - v, 1, 1);
    }

    // 2) epoch ms/sec
    if (v >= 1000000000) {
      final dt = (v >= 1000000000000)
          ? DateTime.fromMillisecondsSinceEpoch(v)
          : DateTime.fromMillisecondsSinceEpoch(v * 1000);
      if (dt.isAfter(DateTime.now())) return null;
      if (dt.year < 1900) return null;
      return DateTime(dt.year, dt.month, dt.day);
    }

    // 3) 8 digits: try YYYYMMDD, then DDMMYYYY
    if (v >= 10000000 && v <= 99999999) {
      final s = v.toString().padLeft(8, '0');

      DateTime? tryYmd() {
        final yyyy = int.tryParse(s.substring(0, 4));
        final mm = int.tryParse(s.substring(4, 6));
        final dd = int.tryParse(s.substring(6, 8));
        if (yyyy == null || mm == null || dd == null) return null;
        if (yyyy < 1900 || yyyy > DateTime.now().year) return null;
        if (mm < 1 || mm > 12) return null;
        if (dd < 1 || dd > 31) return null;
        final dt = DateTime(yyyy, mm, dd);
        if (dt.isAfter(DateTime.now())) return null;
        return dt;
      }

      DateTime? tryDmy() {
        final dd = int.tryParse(s.substring(0, 2));
        final mm = int.tryParse(s.substring(2, 4));
        final yyyy = int.tryParse(s.substring(4, 8));
        if (yyyy == null || mm == null || dd == null) return null;
        if (yyyy < 1900 || yyyy > DateTime.now().year) return null;
        if (mm < 1 || mm > 12) return null;
        if (dd < 1 || dd > 31) return null;
        final dt = DateTime(yyyy, mm, dd);
        if (dt.isAfter(DateTime.now())) return null;
        return dt;
      }

      final ymd = tryYmd();
      if (ymd != null) return ymd;

      final dmy = tryDmy();
      if (dmy != null) return dmy;
    }

    return null;
  }

  String _countLabel(int n, bool isRu) {
    if (!isRu) return '$n measurements';
    final nAbs = n.abs() % 100;
    final n1 = nAbs % 10;
    if (nAbs >= 11 && nAbs <= 14) return '$n измерений';
    if (n1 == 1) return '$n измерение';
    if (n1 >= 2 && n1 <= 4) return '$n измерения';
    return '$n измерений';
  }

  List<BloodPressureRecord> _filterByPeriod(List<BloodPressureRecord> records, int periodDays) {
    if (records.isEmpty) return const [];
    if (periodDays <= 0) return records;

    final now = DateTime.now();
    final from = DateTime(now.year, now.month, now.day).subtract(Duration(days: periodDays - 1));
    return records.where((r) => !r.dateTime.isBefore(from)).toList();
  }

  _Stats _calcStats(List<BloodPressureRecord> records, int targetSys, int targetDia) {
    if (records.isEmpty) return _Stats.empty();

    var sumSys = 0;
    var sumDia = 0;
    var minSys = records.first.systolic;
    var maxSys = records.first.systolic;
    var minDia = records.first.diastolic;
    var maxDia = records.first.diastolic;

    var outCount = 0;

    for (final r in records) {
      final sys = r.systolic;
      final dia = r.diastolic;

      sumSys += sys;
      sumDia += dia;

      if (sys < minSys) minSys = sys;
      if (sys > maxSys) maxSys = sys;

      if (dia < minDia) minDia = dia;
      if (dia > maxDia) maxDia = dia;

      if (sys > targetSys || dia > targetDia) outCount++;
    }

    final n = records.length;
    final avgSys = (sumSys / n).round();
    final avgDia = (sumDia / n).round();
    final outPct = (outCount * 100.0 / n);

    return _Stats(
      n: n,
      avgSys: avgSys,
      avgDia: avgDia,
      minSys: minSys,
      maxSys: maxSys,
      minDia: minDia,
      maxDia: maxDia,
      outOfRangeCount: outCount,
      outOfRangePct: outPct,
    );
  }

  _BucketStats _calcBucket(List<BloodPressureRecord> records) {
    if (records.isEmpty) return _BucketStats.empty();

    var sumSys = 0;
    var sumDia = 0;

    for (final r in records) {
      sumSys += r.systolic;
      sumDia += r.diastolic;
    }

    final n = records.length;
    return _BucketStats(
      n: n,
      avgSys: (sumSys / n).round(),
      avgDia: (sumDia / n).round(),
    );
  }

  Map<String, _BucketStats> _calcBuckets(List<BloodPressureRecord> records) {
    final morning = <BloodPressureRecord>[];
    final day = <BloodPressureRecord>[];
    final evening = <BloodPressureRecord>[];
    final night = <BloodPressureRecord>[];

    for (final r in records) {
      final m = _toMinutes(r.dateTime);
      if (m >= _kMorningStart && m < _kMorningEnd) {
        morning.add(r);
      } else if (m >= _kDayStart && m < _kDayEnd) {
        day.add(r);
      } else if (m >= _kEveningStart && m < _kEveningEnd) {
        evening.add(r);
      } else {
        night.add(r);
      }
    }

    return {
      'morning': _calcBucket(morning),
      'day': _calcBucket(day),
      'evening': _calcBucket(evening),
      'night': _calcBucket(night),
    };
  }

  Future<void> _exportToPDFDoctorReport({
    required List<BloodPressureRecord> records,
    required String languageCode,
    required UserProfile? profile,
    required int periodDays,
  }) async {
    final isRu = languageCode == 'ru';

    final fontData = await rootBundle.load("assets/fonts/Inter-Regular.ttf");
    final ttf = pw.Font.ttf(fontData);
    final boldFontData = await rootBundle.load("assets/fonts/Inter-Bold.ttf");
    final ttfBold = pw.Font.ttf(boldFontData);

    final filtered = _filterByPeriod(records, periodDays);

    final targetSys = profile?.targetSystolic ?? 120;
    final targetDia = profile?.targetDiastolic ?? 80;

    final name = (profile?.name ?? '').trim().isEmpty ? '—' : profile!.name.trim();
    final age = _computeAge(profile);
    final ageText = age == null ? '—' : age.toString();

    DateTime? maxDt;
    DateTime? minDt;
    if (filtered.isNotEmpty) {
      maxDt = filtered.map((e) => e.dateTime).reduce((a, b) => a.isAfter(b) ? a : b);
      minDt = filtered.map((e) => e.dateTime).reduce((a, b) => a.isBefore(b) ? a : b);
    }

    final periodText = (minDt == null || maxDt == null)
        ? (isRu ? 'Период: —' : 'Period: —')
        : (isRu
        ? 'Период: ${_fmtDate(minDt)} — ${_fmtDate(maxDt)}'
        : 'Period: ${_fmtDate(minDt)} — ${_fmtDate(maxDt)}');

    final stats = _calcStats(filtered, targetSys, targetDia);
    final buckets = _calcBuckets(filtered);

    final title = isRu ? 'Отчёт по артериальному давлению' : 'Blood Pressure Report';

    final pdf = pw.Document();

    final h1 = pw.TextStyle(font: ttfBold, fontSize: 18, color: PdfColors.blue900);
    final h2 = pw.TextStyle(font: ttfBold, fontSize: 12, color: PdfColors.blue900);
    final body = pw.TextStyle(font: ttf, fontSize: 10, color: PdfColors.black);
    final bodyBold = pw.TextStyle(font: ttfBold, fontSize: 10, color: PdfColors.black);
    final small = pw.TextStyle(font: ttf, fontSize: 8, color: PdfColors.grey700);

    pw.Widget sectionTitle(String text) => pw.Padding(
      padding: const pw.EdgeInsets.only(top: 10, bottom: 6),
      child: pw.Text(text, style: h2),
    );

    pw.Widget kvLine(String k, String v) => pw.Row(
      children: [
        pw.Expanded(child: pw.Text(k, style: body)),
        pw.Text(v, style: bodyBold),
      ],
    );

    pw.Widget statBox() {
      final avg = stats.isEmpty ? '—' : '${stats.avgSys}/${stats.avgDia}';
      final min = stats.isEmpty ? '—' : '${stats.minSys}/${stats.minDia}';
      final max = stats.isEmpty ? '—' : '${stats.maxSys}/${stats.maxDia}';
      final out = stats.isEmpty
          ? '—'
          : '${stats.outOfRangePct.toStringAsFixed(0)}% (${stats.outOfRangeCount}/${stats.n})';

      final avgLabel = isRu ? 'Среднее за период' : 'Average';
      final minLabel = isRu ? 'Минимум' : 'Min';
      final maxLabel = isRu ? 'Максимум' : 'Max';
      final outLabel = isRu ? 'Выше нормы' : 'Above target';

      return pw.Container(
        decoration: pw.BoxDecoration(
          borderRadius: pw.BorderRadius.circular(8),
          color: PdfColors.grey100,
          border: pw.Border.all(color: PdfColors.grey300, width: 1),
        ),
        padding: const pw.EdgeInsets.all(10),
        child: pw.Column(
          crossAxisAlignment: pw.CrossAxisAlignment.start,
          children: [
            kvLine(avgLabel, avg),
            pw.SizedBox(height: 4),
            kvLine(minLabel, min),
            pw.SizedBox(height: 4),
            kvLine(maxLabel, max),
            pw.SizedBox(height: 4),
            kvLine(outLabel, out),
          ],
        ),
      );
    }

    pw.Widget bucketTable() {
      final morning = buckets['morning']!;
      final day = buckets['day']!;
      final evening = buckets['evening']!;
      final night = buckets['night']!;

      String f(_BucketStats b) {
        if (b.isEmpty) return '—';
        return '${b.avgSys}/${b.avgDia}  (${_countLabel(b.n, isRu)})';
      }

      final rows = [
        [isRu ? 'Утро (06–10)' : 'Morning (06–10)', f(morning)],
        [isRu ? 'День (12–16)' : 'Day (12–16)', f(day)],
        [isRu ? 'Вечер (18–22)' : 'Evening (18–22)', f(evening)],
        [isRu ? 'Ночь (22–06)' : 'Night (22–06)', f(night)],
      ];

      return pw.TableHelper.fromTextArray(
        headers: [isRu ? 'Время суток' : 'Time of day', isRu ? 'Среднее (SYS/DIA)' : 'Average (SYS/DIA)'],
        data: rows,
        headerStyle: pw.TextStyle(font: ttfBold, fontSize: 10, color: PdfColors.white),
        headerDecoration: const pw.BoxDecoration(color: PdfColors.blue800),
        cellStyle: body,
        cellAlignment: pw.Alignment.centerLeft,
        columnWidths: {
          0: const pw.FlexColumnWidth(2),
          1: const pw.FlexColumnWidth(3),
        },
        cellPadding: const pw.EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      );
    }

    pw.Widget entriesTable() {
      final sorted = List<BloodPressureRecord>.from(filtered)
        ..sort((a, b) => b.dateTime.compareTo(a.dateTime));

      final headers = isRu
          ? ['Дата', 'Время', 'Давление', 'Пульс', 'Примечания']
          : ['Date', 'Time', 'BP', 'Pulse', 'Notes'];

      final data = sorted.map((r) {
        final note = (r.note ?? '').trim();
        return [
          _fmtDate(r.dateTime),
          _fmtTime(r.dateTime),
          '${r.systolic}/${r.diastolic}',
          r.pulse.toString(),
          note,
        ];
      }).toList();

      return pw.TableHelper.fromTextArray(
        headers: headers,
        data: data,
        headerStyle: pw.TextStyle(font: ttfBold, fontSize: 10, color: PdfColors.white),
        headerDecoration: const pw.BoxDecoration(color: PdfColors.blue800),
        cellStyle: body,
        cellAlignment: pw.Alignment.center,
        cellPadding: const pw.EdgeInsets.symmetric(horizontal: 6, vertical: 4),
        columnWidths: {
          0: const pw.FixedColumnWidth(70),
          1: const pw.FixedColumnWidth(46),
          2: const pw.FixedColumnWidth(60),
          3: const pw.FixedColumnWidth(44),
          4: const pw.FlexColumnWidth(),
        },
      );
    }

    pw.Widget doctorNotes() {
      final label = isRu ? 'Заметки врача:' : "Doctor's notes:";
      return pw.Column(
        crossAxisAlignment: pw.CrossAxisAlignment.start,
        children: [
          pw.Text(label, style: bodyBold),
          pw.SizedBox(height: 6),
          for (int i = 0; i < 6; i++)
            pw.Container(
              margin: const pw.EdgeInsets.only(bottom: 6),
              height: 10,
              decoration: const pw.BoxDecoration(
                border: pw.Border(bottom: pw.BorderSide(color: PdfColors.grey500, width: 0.7)),
              ),
            ),
        ],
      );
    }

    final disclaimerRu =
        'Данные внесены пользователем и не являются медицинским измерением. Интерпретация требует клинической верификации.';
    final disclaimerEn =
        'Data is user-entered and does not replace a clinical measurement. Interpretation requires medical verification.';

    pdf.addPage(
      pw.MultiPage(
        pageFormat: PdfPageFormat.a4,
        margin: const pw.EdgeInsets.all(32),
        build: (_) => [
          pw.Text(title, style: h1),
          pw.SizedBox(height: 6),
          pw.Text(periodText, style: body),
          pw.SizedBox(height: 8),
          pw.Row(
            children: [
              pw.Expanded(child: pw.Text(isRu ? 'Пациент: $name' : 'Patient: $name', style: body)),
              pw.Text(isRu ? 'Возраст: $ageText' : 'Age: $ageText', style: body),
            ],
          ),
          pw.SizedBox(height: 6),
          pw.Text(
            isRu ? 'Целевые значения: $targetSys/$targetDia' : 'Targets: $targetSys/$targetDia',
            style: body,
          ),
          sectionTitle(isRu ? 'Резюме' : 'Summary'),
          statBox(),
          sectionTitle(isRu ? 'Аналитика по времени суток' : 'Time-of-day analysis'),
          bucketTable(),
          sectionTitle(isRu ? 'Журнал измерений' : 'Measurements log'),
          entriesTable(),
          pw.SizedBox(height: 12),
          doctorNotes(),
          pw.SizedBox(height: 10),
          pw.Text(isRu ? disclaimerRu : disclaimerEn, style: small),
        ],
      ),
    );

    final directory = await getTemporaryDirectory();
    final ts = DateTime.now().toIso8601String().replaceAll(':', '-');
    final file = File('${directory.path}/pressure_report_$ts.pdf');
    await file.writeAsBytes(await pdf.save());

    await Share.shareXFiles([XFile(file.path)], text: isRu ? 'Отчёт (PDF)' : 'Report (PDF)');
  }
}

class _Stats {
  final int n;
  final int avgSys;
  final int avgDia;
  final int minSys;
  final int maxSys;
  final int minDia;
  final int maxDia;
  final int outOfRangeCount;
  final double outOfRangePct;

  const _Stats({
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

  bool get isEmpty => n == 0;

  factory _Stats.empty() => const _Stats(
    n: 0,
    avgSys: 0,
    avgDia: 0,
    minSys: 0,
    maxSys: 0,
    minDia: 0,
    maxDia: 0,
    outOfRangeCount: 0,
    outOfRangePct: 0.0,
  );
}

class _BucketStats {
  final int n;
  final int avgSys;
  final int avgDia;

  const _BucketStats({
    required this.n,
    required this.avgSys,
    required this.avgDia,
  });

  bool get isEmpty => n == 0;

  factory _BucketStats.empty() => const _BucketStats(n: 0, avgSys: 0, avgDia: 0);
}
