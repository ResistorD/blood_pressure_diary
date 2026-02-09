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
      'This action will replace all current app data (profile, settings, and pressure records). Continue?';

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
  String get avgLabel => 'Avg:';

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
  String get bpLevelHtn1 => 'Hypertension 1';

  @override
  String get bpLevelHtn2 => 'Hypertension 2';

  @override
  String get bpLevelCrisis => 'Crisis';

  @override
  String get notifTitleMeasureNow => 'Time to measure blood pressure';

  @override
  String get notifBodyDontForget =>
      'Don’t forget to log your measurements to track your health.';

  @override
  String get notifChannelName => 'Blood pressure reminders';

  @override
  String get notifChannelDescription =>
      'Daily reminders to measure blood pressure';

  @override
  String get profileAccount => 'Account';

  @override
  String get profileConnect => 'Connect';

  @override
  String get profileNotSignedIn => 'You are not signed in';

  @override
  String get profileSignIn => 'Sign in';

  @override
  String get profileLinked => 'Account connected';

  @override
  String get profileSignOut => 'Sign out';

  @override
  String get profileChooseSignIn => 'Choose a sign-in method';

  @override
  String get profileSystolicLabel => 'Systolic';

  @override
  String get profileDiastolicLabel => 'Diastolic';

  @override
  String get premiumRemoveAds => 'Remove ads';

  @override
  String get premiumSubtitleOneTime => 'One-time payment €2.99 — forever';

  @override
  String get dobLabel => 'Date of birth';

  @override
  String get genderShortMale => 'M';

  @override
  String get genderShortFemale => 'F';

  @override
  String get appTitle => 'BP Diary';

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
  String get addRecord => 'New Record';

  @override
  String get save => 'Save';

  @override
  String get cancel => 'Cancel';

  @override
  String get settings => 'Settings';

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
    return 'Last measurement: $date';
  }
}
