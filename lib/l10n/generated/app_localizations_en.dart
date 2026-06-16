// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get backupJson => 'Backup (JSON)';

  @override
  String get restoreFromBackup => 'Restore from backup';

  @override
  String get restoreDialogTitle => 'Restore from backup';

  @override
  String get restoreDialogBody =>
      'This will replace all current app data (profile, settings, and blood pressure records). Continue?';

  @override
  String get restoreAction => 'Restore';

  @override
  String get dataRestoredSnack => 'Data restored';

  @override
  String get reminderMorning => 'Morning';

  @override
  String get reminderEvening => 'Evening';

  @override
  String get reminderTime => 'Time';

  @override
  String get languageRu => 'Russian';

  @override
  String get languageEn => 'English';

  @override
  String get noRecordsForPeriod => 'No records for the selected period';

  @override
  String get noDataForPeriod => 'No data for this period';

  @override
  String get noData => 'No data';

  @override
  String get chartsTitle => 'Charts';

  @override
  String get tabPressure => 'Pressure';

  @override
  String get tabPulse => 'Pulse';

  @override
  String get periodWeek => 'Week';

  @override
  String get periodMonth => 'Month';

  @override
  String get periodAll => 'All';

  @override
  String get avgLabel => 'Average:';

  @override
  String get maxLabelShort => 'Max:';

  @override
  String get minLabelShort => 'Min:';

  @override
  String get bpmUnit => 'bpm';

  @override
  String get tagHeader => 'Tags';

  @override
  String tagHeaderWithCount(int count) {
    return 'Tags ($count)';
  }

  @override
  String get tagAfterCoffee => 'After coffee';

  @override
  String get tagAlcohol => 'Alcohol';

  @override
  String get tagAfterMeal => 'After meal';

  @override
  String get tagAfterWalk => 'After walk';

  @override
  String get tagAfterTraining => 'After workout';

  @override
  String get tagStress => 'Stress';

  @override
  String get tagBadSleep => 'Poor sleep';

  @override
  String get tagHeadache => 'Headache';

  @override
  String get tagTookMeds => 'Took meds';

  @override
  String get tagMissedDose => 'Missed dose';

  @override
  String get bpLevelLow => 'Low';

  @override
  String get bpLevelNormal => 'Normal';

  @override
  String get bpLevelElevated => 'Elevated';

  @override
  String get bpLevelHtn1 => 'Hypertension (Stage 1)';

  @override
  String get bpLevelHtn2 => 'Hypertension (Stage 2)';

  @override
  String get bpLevelCrisis => 'Hypertension (Stage 3)';

  @override
  String get notifTitleMeasureNow => 'Time to measure';

  @override
  String get notifBodyDontForget => 'Don’t forget to log your blood pressure.';

  @override
  String get notifChannelName => 'Reminders';

  @override
  String get notifChannelDescription => 'Blood pressure measurement reminders';

  @override
  String get profileAccount => 'Account';

  @override
  String get profileConnect => 'Connect';

  @override
  String get profileNotSignedIn => 'Not signed in';

  @override
  String get profileSignIn => 'Sign in';

  @override
  String get profileLinked => 'Connected';

  @override
  String get profileSignOut => 'Sign out';

  @override
  String get profileChooseSignIn => 'Choose sign-in method';

  @override
  String get profileSystolicLabel => 'Systolic';

  @override
  String get profileDiastolicLabel => 'Diastolic';

  @override
  String get premiumRemoveAds => 'Remove ads';

  @override
  String get premiumSubtitleOneTime => 'One-time purchase';

  @override
  String get dobLabel => 'Date of birth';

  @override
  String get genderShortMale => 'M';

  @override
  String get genderShortFemale => 'F';

  @override
  String get appTitle => 'Blood Pressure Diary';

  @override
  String get yourCondition => 'Your condition';

  @override
  String get normalStatus => 'Normal';

  @override
  String get history => 'History';

  @override
  String get systolic => 'Systolic';

  @override
  String get diastolic => 'Diastolic';

  @override
  String get pulse => 'Pulse';

  @override
  String get addRecord => 'Add record';

  @override
  String get save => 'Save';

  @override
  String get cancel => 'Cancel';

  @override
  String get settings => 'Settings';

  @override
  String get today => 'Today';

  @override
  String get week => 'Week';

  @override
  String get month => 'Month';

  @override
  String get allShort => 'All';

  @override
  String get allTime => 'All time';

  @override
  String get myDiary => 'My diary';

  @override
  String recordsOne(Object count) {
    return '$count record';
  }

  @override
  String recordsFew(Object count) {
    return '$count records';
  }

  @override
  String recordsMany(Object count) {
    return '$count records';
  }

  @override
  String get profile => 'Profile';

  @override
  String get language => 'Language';

  @override
  String get theme => 'Theme';

  @override
  String get unitMmHg => 'mmHg';

  @override
  String get unitBpm => 'bpm';

  @override
  String get noRecords => 'No records yet';

  @override
  String lastMeasurement(String date) {
    return 'Last measurement';
  }

  @override
  String get pickTime => 'Pick time';

  @override
  String get pickDate => 'Pick date';

  @override
  String get deleteRecordQ => 'Delete this record?';

  @override
  String get cannotUndo => 'This action cannot be undone.';

  @override
  String get delete => 'Delete';

  @override
  String get commentHint => 'Comment';

  @override
  String get newRecord => 'New record';

  @override
  String get systolicShort => 'SYS';

  @override
  String get diastolicShort => 'DIA';

  @override
  String get reminders => 'Reminders';

  @override
  String get addReminder => 'Add reminder';

  @override
  String get clearData => 'Clear data';

  @override
  String get clearDataConfirm => 'Delete all data? This cannot be undone.';

  @override
  String get export => 'Export';

  @override
  String get exportCSV => 'Export CSV';

  @override
  String get exportPDF => 'Export PDF';

  @override
  String get contactSupport => 'Contact support';

  @override
  String get rateApp => 'Rate the app';

  @override
  String get versionLabel => 'Version:';

  @override
  String get yes => 'Yes';

  @override
  String get no => 'No';

  @override
  String get light => 'Light';

  @override
  String get dark => 'Dark';

  @override
  String get system => 'System';

  @override
  String get privacyPolicy => 'Privacy Policy';

  @override
  String get privacyPolicyLastUpdate => 'Last updated:';

  @override
  String get privacyPolicyFullText =>
      'We respect your privacy.\n\nWhat the app stores\n• Blood pressure records (systolic/diastolic), pulse, date/time.\n• Optional notes and tags.\n• Settings (language, theme, reminders).\n\nWhere data is stored\n• By default, all data is stored locally on your device.\n\nReminders\n• If you enable reminders, the app schedules local notifications on your device.\n• The app does not transmit your measurements to a server to trigger reminders.\n\nBackups and export\n• When you create a backup (JSON) or export (PDF/CSV), the app prepares a file on your device.\n• If you share that file via other apps, those apps handle the data according to their own privacy policies.\n\nAnalytics and ads\n• The app does not intentionally sell personal data.\n• If third‑party services (e.g., sign‑in providers or store billing) are used, they may process limited technical information needed to provide their service.\n\nYour choices\n• You can delete records and clear all app data from within the app.\n• You can disable reminders at any time.\n\nContact\n• If you contact support, the information you send (email content) is processed by your email provider.\n\nThis text is provided for informational purposes and may be updated as the app evolves.';

  @override
  String get averageLabel => 'Average';

  @override
  String get minLabel => 'Min';

  @override
  String get maxLabel => 'Max';

  @override
  String get pressureLabel => 'Pressure';

  @override
  String get restoreBackupTitle => 'Restore from backup';

  @override
  String get restoreBackupConfirm =>
      'This will replace your current data. Continue?';

  @override
  String get restore => 'Restore';

  @override
  String get dataRestored => 'Data restored';

  @override
  String get morning => 'Morning';

  @override
  String get evening => 'Evening';

  @override
  String get aboutApp => 'About app';

  @override
  String get appAboutText =>
      'Pressure Diary is a blood pressure and pulse log. Data is entered by the user and may help track trends.';

  @override
  String get version => 'Version';

  @override
  String get supportProject => 'Support the project';

  @override
  String get supportProjectHint => 'A voluntary thank-you to the developer';

  @override
  String get emailClientNotFound => 'No email app found';

  @override
  String get actionFailed => 'Action failed';

  @override
  String get time => 'Time';

  @override
  String get supportProjectText =>
      'If the app is useful, you can support development. This is not a subscription or obligation. Even sharing the app already helps 🙂';

  @override
  String get supportCoffee => '€2 — coffee';

  @override
  String get supportCoffeeHint => 'Small thank-you';

  @override
  String get supportPizza => '€3 — pizza';

  @override
  String get supportPizzaHint => 'A bit more generous';

  @override
  String get supportBurger => '€5 — burger';

  @override
  String get supportBurgerHint => 'Maximum civic virtue';

  @override
  String get shareApp => 'Share the app';

  @override
  String get shareAppHint => 'Share Pressure Diary with friends';

  @override
  String get shareAppText => 'App link:';

  @override
  String get russian => 'Russian';

  @override
  String get account => 'Account';

  @override
  String get accountConnected => 'Connected';

  @override
  String get accountNotConnected => 'Not connected';

  @override
  String get chooseSignIn => 'Choose sign-in method';

  @override
  String get connect => 'Connect';

  @override
  String get signIn => 'Sign in';

  @override
  String get signOut => 'Sign out';

  @override
  String get name => 'Name';

  @override
  String get gender => 'Gender';

  @override
  String get maleShort => 'M';

  @override
  String get femaleShort => 'F';

  @override
  String get birthDate => 'Date of birth';

  @override
  String get pressureNorms => 'Target pressure';

  @override
  String get upper => 'Upper';

  @override
  String get lower => 'Lower';

  @override
  String get removeAds => 'Remove ads';

  @override
  String get removeAdsSubtitle => 'One-time purchase';

  @override
  String get bpm => 'bpm';

  @override
  String get accountLinked => 'Account linked';

  @override
  String get notSignedIn => 'You are not signed in';

  @override
  String get link => 'Link';

  @override
  String get buyPremium => 'Remove ads';

  @override
  String get oneTimePayment => 'One-time payment €2.99 — lifetime';

  @override
  String get male => 'Male';

  @override
  String get female => 'Female';
}
