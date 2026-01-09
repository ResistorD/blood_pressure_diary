import 'dart:io';
import 'package:flutter/services.dart';
import 'package:csv/csv.dart';
import 'package:path_provider/path_provider.dart';
import 'package:pdf/pdf.dart';
import 'package:pdf/widgets.dart' as pw;
import 'package:share_plus/share_plus.dart';
import 'package:intl/intl.dart';
import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';

enum ExportFormat { csv, pdf }

class ExportService {
  Future<void> exportData(List<BloodPressureRecord> records, ExportFormat format, String languageCode) async {
    if (format == ExportFormat.csv) {
      await _exportToCSV(records);
    } else {
      await _exportToPDF(records, languageCode);
    }
  }

  Future<void> _exportToCSV(List<BloodPressureRecord> records) async {
    final List<List<dynamic>> rows = [
      ['Date', 'Time', 'Systolic', 'Diastolic', 'Pulse', 'Note']
    ];

    for (var record in records) {
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

  Future<void> _exportToPDF(List<BloodPressureRecord> records, String languageCode) async {
    final pdf = pw.Document();

    // Загрузка шрифта Inter для поддержки кириллицы
    final fontData = await rootBundle.load("assets/fonts/Inter-Regular.ttf");
    final ttf = pw.Font.ttf(fontData);
    final boldFontData = await rootBundle.load("assets/fonts/Inter-Bold.ttf");
    final ttfBold = pw.Font.ttf(boldFontData);

    final isRu = languageCode == 'ru';
    final title = isRu ? 'Дневник давления' : 'Blood Pressure Diary';
    final headers = isRu 
        ? ['Дата', 'Время', 'СИС', 'ДИА', 'Пульс', 'Заметка']
        : ['Date', 'Time', 'SYS', 'DIA', 'Pulse', 'Note'];

    pdf.addPage(
      pw.MultiPage(
        pageFormat: PdfPageFormat.a4,
        margin: const pw.EdgeInsets.all(32),
        build: (context) => [
          pw.Header(
            level: 0,
            child: pw.Row(
              mainAxisAlignment: pw.MainAxisAlignment.spaceBetween,
              children: [
                pw.Text(title, style: pw.TextStyle(font: ttfBold, fontSize: 24, color: PdfColors.blue900)),
                pw.Text(DateFormat('dd.MM.yyyy').format(DateTime.now()), style: pw.TextStyle(font: ttf, fontSize: 12)),
              ],
            ),
          ),
          pw.SizedBox(height: 20),
          pw.TableHelper.fromTextArray(
            headers: headers,
            data: records.map((r) => [
              DateFormat('dd.MM.yyyy').format(r.dateTime),
              DateFormat('HH:mm').format(r.dateTime),
              r.systolic.toString(),
              r.diastolic.toString(),
              r.pulse.toString(),
              r.note ?? '',
            ]).toList(),
            headerStyle: pw.TextStyle(font: ttfBold, color: PdfColors.white),
            headerDecoration: const pw.BoxDecoration(color: PdfColors.blue800),
            cellStyle: pw.TextStyle(font: ttf),
            cellAlignment: pw.Alignment.center,
            columnWidths: {
              0: const pw.FixedColumnWidth(80),
              1: const pw.FixedColumnWidth(60),
              2: const pw.FixedColumnWidth(40),
              3: const pw.FixedColumnWidth(40),
              4: const pw.FixedColumnWidth(50),
              5: const pw.FlexColumnWidth(),
            },
          ),
        ],
      ),
    );

    final directory = await getTemporaryDirectory();
    final file = File('${directory.path}/blood_pressure_export.pdf');
    await file.writeAsBytes(await pdf.save());

    await Share.shareXFiles([XFile(file.path)], text: 'Blood Pressure Export (PDF)');
  }
}
