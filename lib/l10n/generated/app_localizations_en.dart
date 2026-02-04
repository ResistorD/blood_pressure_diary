// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get settings => 'Settings';

  @override
  String get selectLanguage => 'Select Language';

  @override
  String get appTitle => 'Blood Pressure Diary';

  @override
  String get notifications => 'Notifications';

  @override
  String get clearData => 'Clear Data';

  @override
  String get aboutApp => 'About App';

  @override
  String version(String version) {
    return 'Version $version';
  }

  @override
  String get functionInDevelopment => 'Function in development';

  @override
  String get deleteRecordQ => 'Delete record?';

  @override
  String get cannotUndo => 'This action cannot be undone.';

  @override
  String get cancel => 'Cancel';

  @override
  String get delete => 'Delete';

  @override
  String get theme => 'Theme';

  @override
  String get language => 'Язык';

  @override
  String get light => 'Light';

  @override
  String get dark => 'Dark';

  @override
  String get system => 'System';

  @override
  String get reminders => 'Reminders';

  @override
  String get addReminder => 'Add time';

  @override
  String get clearDataConfirm =>
      'Are you sure you want to delete all records? This action cannot be undone.';

  @override
  String get yes => 'Yes';

  @override
  String get no => 'No';

  @override
  String get export => 'Export Data';

  @override
  String get exportCSV => 'CSV Spreadsheet';

  @override
  String get exportPDF => 'PDF Report';

  @override
  String get contactSupport => 'Contact Support';

  @override
  String get rateApp => 'Rate App';

  @override
  String get supportEmail => 'your_email@mail.com';

  @override
  String get profile => 'Profile';

  @override
  String get name => 'Name';

  @override
  String get age => 'Age';

  @override
  String get gender => 'Gender';

  @override
  String get weight => 'Weight';

  @override
  String get male => 'Male';

  @override
  String get female => 'Female';

  @override
  String get other => 'Other';

  @override
  String get myGoal => 'My Goal';

  @override
  String get targetPressure => 'Target Pressure';

  @override
  String get systolic => 'Systolic';

  @override
  String get diastolic => 'Diastolic';

  @override
  String get premium => 'Premium';

  @override
  String get oneTimePayment => 'One-time payment 2,99 €';

  @override
  String get buyPremium => 'Buy Premium';

  @override
  String get save => 'Save';
}
