import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:intl/intl.dart' as intl;

import 'app_localizations_en.dart';
import 'app_localizations_ru.dart';

// ignore_for_file: type=lint

/// Callers can lookup localized strings with an instance of AppLocalizations
/// returned by `AppLocalizations.of(context)`.
///
/// Applications need to include `AppLocalizations.delegate()` in their app's
/// `localizationDelegates` list, and the locales they support in the app's
/// `supportedLocales` list. For example:
///
/// ```dart
/// import 'generated/app_localizations.dart';
///
/// return MaterialApp(
///   localizationsDelegates: AppLocalizations.localizationsDelegates,
///   supportedLocales: AppLocalizations.supportedLocales,
///   home: MyApplicationHome(),
/// );
/// ```
///
/// ## Update pubspec.yaml
///
/// Please make sure to update your pubspec.yaml to include the following
/// packages:
///
/// ```yaml
/// dependencies:
///   # Internationalization support.
///   flutter_localizations:
///     sdk: flutter
///   intl: any # Use the pinned version from flutter_localizations
///
///   # Rest of dependencies
/// ```
///
/// ## iOS Applications
///
/// iOS applications define key application metadata, including supported
/// locales, in an Info.plist file that is built into the application bundle.
/// To configure the locales supported by your app, you’ll need to edit this
/// file.
///
/// First, open your project’s ios/Runner.xcworkspace Xcode workspace file.
/// Then, in the Project Navigator, open the Info.plist file under the Runner
/// project’s Runner folder.
///
/// Next, select the Information Property List item, select Add Item from the
/// Editor menu, then select Localizations from the pop-up menu.
///
/// Select and expand the newly-created Localizations item then, for each
/// locale your application supports, add a new item and select the locale
/// you wish to add from the pop-up menu in the Value field. This list should
/// be consistent with the languages listed in the AppLocalizations.supportedLocales
/// property.
abstract class AppLocalizations {
  AppLocalizations(String locale)
    : localeName = intl.Intl.canonicalizedLocale(locale.toString());

  final String localeName;

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  /// A list of this localizations delegate along with the default localizations
  /// delegates.
  ///
  /// Returns a list of localizations delegates containing this delegate along with
  /// GlobalMaterialLocalizations.delegate, GlobalCupertinoLocalizations.delegate,
  /// and GlobalWidgetsLocalizations.delegate.
  ///
  /// Additional delegates can be added by appending to this list in
  /// MaterialApp. This list does not have to be used at all if a custom list
  /// of delegates is preferred or required.
  static const List<LocalizationsDelegate<dynamic>> localizationsDelegates =
      <LocalizationsDelegate<dynamic>>[
        delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
      ];

  /// A list of this localizations delegate's supported locales.
  static const List<Locale> supportedLocales = <Locale>[
    Locale('en'),
    Locale('ru'),
  ];

  /// No description provided for @settings.
  ///
  /// In ru, this message translates to:
  /// **'Настройки'**
  String get settings;

  /// No description provided for @selectLanguage.
  ///
  /// In ru, this message translates to:
  /// **'Выбор языка'**
  String get selectLanguage;

  /// No description provided for @appTitle.
  ///
  /// In ru, this message translates to:
  /// **'Дневник давления'**
  String get appTitle;

  /// No description provided for @notifications.
  ///
  /// In ru, this message translates to:
  /// **'Уведомления'**
  String get notifications;

  /// No description provided for @clearData.
  ///
  /// In ru, this message translates to:
  /// **'Очистить данные'**
  String get clearData;

  /// No description provided for @aboutApp.
  ///
  /// In ru, this message translates to:
  /// **'О приложении'**
  String get aboutApp;

  /// No description provided for @version.
  ///
  /// In ru, this message translates to:
  /// **'Версия {version}'**
  String version(String version);

  /// No description provided for @functionInDevelopment.
  ///
  /// In ru, this message translates to:
  /// **'Функция в разработке'**
  String get functionInDevelopment;

  /// No description provided for @deleteRecordQ.
  ///
  /// In ru, this message translates to:
  /// **'Удалить запись?'**
  String get deleteRecordQ;

  /// No description provided for @cannotUndo.
  ///
  /// In ru, this message translates to:
  /// **'Это действие нельзя отменить.'**
  String get cannotUndo;

  /// No description provided for @cancel.
  ///
  /// In ru, this message translates to:
  /// **'Отмена'**
  String get cancel;

  /// No description provided for @delete.
  ///
  /// In ru, this message translates to:
  /// **'Удалить'**
  String get delete;

  /// No description provided for @theme.
  ///
  /// In ru, this message translates to:
  /// **'Тема'**
  String get theme;

  /// No description provided for @light.
  ///
  /// In ru, this message translates to:
  /// **'Светлая'**
  String get light;

  /// No description provided for @dark.
  ///
  /// In ru, this message translates to:
  /// **'Темная'**
  String get dark;

  /// No description provided for @system.
  ///
  /// In ru, this message translates to:
  /// **'Системная'**
  String get system;

  /// No description provided for @reminders.
  ///
  /// In ru, this message translates to:
  /// **'Напоминания'**
  String get reminders;

  /// No description provided for @addReminder.
  ///
  /// In ru, this message translates to:
  /// **'Добавить время'**
  String get addReminder;

  /// No description provided for @clearDataConfirm.
  ///
  /// In ru, this message translates to:
  /// **'Вы уверены, что хотите удалить все записи? Это действие нельзя отменить.'**
  String get clearDataConfirm;

  /// No description provided for @yes.
  ///
  /// In ru, this message translates to:
  /// **'Да'**
  String get yes;

  /// No description provided for @no.
  ///
  /// In ru, this message translates to:
  /// **'Нет'**
  String get no;

  /// No description provided for @export.
  ///
  /// In ru, this message translates to:
  /// **'Экспорт данных'**
  String get export;

  /// No description provided for @exportCSV.
  ///
  /// In ru, this message translates to:
  /// **'CSV Таблица'**
  String get exportCSV;

  /// No description provided for @exportPDF.
  ///
  /// In ru, this message translates to:
  /// **'PDF Отчет'**
  String get exportPDF;

  /// No description provided for @contactSupport.
  ///
  /// In ru, this message translates to:
  /// **'Написать нам'**
  String get contactSupport;

  /// No description provided for @rateApp.
  ///
  /// In ru, this message translates to:
  /// **'Оценить приложение'**
  String get rateApp;

  /// No description provided for @supportEmail.
  ///
  /// In ru, this message translates to:
  /// **'your_email@mail.com'**
  String get supportEmail;

  /// No description provided for @profile.
  ///
  /// In ru, this message translates to:
  /// **'Профиль'**
  String get profile;

  /// No description provided for @name.
  ///
  /// In ru, this message translates to:
  /// **'Имя'**
  String get name;

  /// No description provided for @age.
  ///
  /// In ru, this message translates to:
  /// **'Возраст'**
  String get age;

  /// No description provided for @gender.
  ///
  /// In ru, this message translates to:
  /// **'Пол'**
  String get gender;

  /// No description provided for @weight.
  ///
  /// In ru, this message translates to:
  /// **'Вес'**
  String get weight;

  /// No description provided for @male.
  ///
  /// In ru, this message translates to:
  /// **'Мужской'**
  String get male;

  /// No description provided for @female.
  ///
  /// In ru, this message translates to:
  /// **'Женский'**
  String get female;

  /// No description provided for @other.
  ///
  /// In ru, this message translates to:
  /// **'Другой'**
  String get other;

  /// No description provided for @myGoal.
  ///
  /// In ru, this message translates to:
  /// **'Моя цель'**
  String get myGoal;

  /// No description provided for @targetPressure.
  ///
  /// In ru, this message translates to:
  /// **'Целевое давление'**
  String get targetPressure;

  /// No description provided for @systolic.
  ///
  /// In ru, this message translates to:
  /// **'Систолическое'**
  String get systolic;

  /// No description provided for @diastolic.
  ///
  /// In ru, this message translates to:
  /// **'Диастолическое'**
  String get diastolic;

  /// No description provided for @premium.
  ///
  /// In ru, this message translates to:
  /// **'Премиум'**
  String get premium;

  /// No description provided for @oneTimePayment.
  ///
  /// In ru, this message translates to:
  /// **'Разовый платеж 2,99 €'**
  String get oneTimePayment;

  /// No description provided for @buyPremium.
  ///
  /// In ru, this message translates to:
  /// **'Купить Премиум'**
  String get buyPremium;

  /// No description provided for @save.
  ///
  /// In ru, this message translates to:
  /// **'Сохранить'**
  String get save;
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(lookupAppLocalizations(locale));
  }

  @override
  bool isSupported(Locale locale) =>
      <String>['en', 'ru'].contains(locale.languageCode);

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}

AppLocalizations lookupAppLocalizations(Locale locale) {
  // Lookup logic when only language code is specified.
  switch (locale.languageCode) {
    case 'en':
      return AppLocalizationsEn();
    case 'ru':
      return AppLocalizationsRu();
  }

  throw FlutterError(
    'AppLocalizations.delegate failed to load unsupported locale "$locale". This is likely '
    'an issue with the localizations generation tool. Please file an issue '
    'on GitHub with a reproducible sample app and the gen-l10n configuration '
    'that was used.',
  );
}
