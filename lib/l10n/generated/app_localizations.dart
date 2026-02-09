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

  /// No description provided for @backupJson.
  ///
  /// In ru, this message translates to:
  /// **'Резервная копия (JSON)'**
  String get backupJson;

  /// No description provided for @restoreFromBackup.
  ///
  /// In ru, this message translates to:
  /// **'Восстановить из копии'**
  String get restoreFromBackup;

  /// No description provided for @restoreDialogTitle.
  ///
  /// In ru, this message translates to:
  /// **'Восстановление из копии'**
  String get restoreDialogTitle;

  /// No description provided for @restoreDialogBody.
  ///
  /// In ru, this message translates to:
  /// **'Это действие заменит все текущие данные приложения (профиль, настройки и записи давления). Продолжить?'**
  String get restoreDialogBody;

  /// No description provided for @restoreAction.
  ///
  /// In ru, this message translates to:
  /// **'Восстановить'**
  String get restoreAction;

  /// No description provided for @dataRestoredSnack.
  ///
  /// In ru, this message translates to:
  /// **'Данные восстановлены'**
  String get dataRestoredSnack;

  /// No description provided for @reminderMorning.
  ///
  /// In ru, this message translates to:
  /// **'Утро'**
  String get reminderMorning;

  /// No description provided for @reminderEvening.
  ///
  /// In ru, this message translates to:
  /// **'Вечер'**
  String get reminderEvening;

  /// No description provided for @reminderTime.
  ///
  /// In ru, this message translates to:
  /// **'Время'**
  String get reminderTime;

  /// No description provided for @languageRu.
  ///
  /// In ru, this message translates to:
  /// **'Русский'**
  String get languageRu;

  /// No description provided for @languageEn.
  ///
  /// In ru, this message translates to:
  /// **'English'**
  String get languageEn;

  /// No description provided for @noRecordsForPeriod.
  ///
  /// In ru, this message translates to:
  /// **'Нет записей за выбранный период'**
  String get noRecordsForPeriod;

  /// No description provided for @noDataForPeriod.
  ///
  /// In ru, this message translates to:
  /// **'Нет данных за этот период'**
  String get noDataForPeriod;

  /// No description provided for @noData.
  ///
  /// In ru, this message translates to:
  /// **'Нет данных'**
  String get noData;

  /// No description provided for @chartsTitle.
  ///
  /// In ru, this message translates to:
  /// **'Графики'**
  String get chartsTitle;

  /// No description provided for @tabPressure.
  ///
  /// In ru, this message translates to:
  /// **'Давление'**
  String get tabPressure;

  /// No description provided for @tabPulse.
  ///
  /// In ru, this message translates to:
  /// **'Пульс'**
  String get tabPulse;

  /// No description provided for @periodWeek.
  ///
  /// In ru, this message translates to:
  /// **'Неделя'**
  String get periodWeek;

  /// No description provided for @periodMonth.
  ///
  /// In ru, this message translates to:
  /// **'Месяц'**
  String get periodMonth;

  /// No description provided for @periodAll.
  ///
  /// In ru, this message translates to:
  /// **'Все'**
  String get periodAll;

  /// No description provided for @avgLabel.
  ///
  /// In ru, this message translates to:
  /// **'Среднее:'**
  String get avgLabel;

  /// No description provided for @maxLabelShort.
  ///
  /// In ru, this message translates to:
  /// **'Макс.:'**
  String get maxLabelShort;

  /// No description provided for @minLabelShort.
  ///
  /// In ru, this message translates to:
  /// **'Мин.:'**
  String get minLabelShort;

  /// No description provided for @bpmUnit.
  ///
  /// In ru, this message translates to:
  /// **'уд/мин'**
  String get bpmUnit;

  /// No description provided for @tagHeader.
  ///
  /// In ru, this message translates to:
  /// **'Теги'**
  String get tagHeader;

  /// No description provided for @tagHeaderWithCount.
  ///
  /// In ru, this message translates to:
  /// **'Теги ({count})'**
  String tagHeaderWithCount(int count);

  /// No description provided for @tagAfterCoffee.
  ///
  /// In ru, this message translates to:
  /// **'После кофе'**
  String get tagAfterCoffee;

  /// No description provided for @tagAlcohol.
  ///
  /// In ru, this message translates to:
  /// **'Алкоголь'**
  String get tagAlcohol;

  /// No description provided for @tagAfterMeal.
  ///
  /// In ru, this message translates to:
  /// **'После еды'**
  String get tagAfterMeal;

  /// No description provided for @tagAfterWalk.
  ///
  /// In ru, this message translates to:
  /// **'После прогулки'**
  String get tagAfterWalk;

  /// No description provided for @tagAfterTraining.
  ///
  /// In ru, this message translates to:
  /// **'После тренировки'**
  String get tagAfterTraining;

  /// No description provided for @tagStress.
  ///
  /// In ru, this message translates to:
  /// **'Стресс'**
  String get tagStress;

  /// No description provided for @tagBadSleep.
  ///
  /// In ru, this message translates to:
  /// **'Плохой сон'**
  String get tagBadSleep;

  /// No description provided for @tagHeadache.
  ///
  /// In ru, this message translates to:
  /// **'Головная боль'**
  String get tagHeadache;

  /// No description provided for @tagTookMeds.
  ///
  /// In ru, this message translates to:
  /// **'Принял лекарство'**
  String get tagTookMeds;

  /// No description provided for @tagMissedDose.
  ///
  /// In ru, this message translates to:
  /// **'Пропустил приём'**
  String get tagMissedDose;

  /// No description provided for @bpLevelLow.
  ///
  /// In ru, this message translates to:
  /// **'Понижено'**
  String get bpLevelLow;

  /// No description provided for @bpLevelNormal.
  ///
  /// In ru, this message translates to:
  /// **'Норма'**
  String get bpLevelNormal;

  /// No description provided for @bpLevelElevated.
  ///
  /// In ru, this message translates to:
  /// **'Повышено'**
  String get bpLevelElevated;

  /// No description provided for @bpLevelHtn1.
  ///
  /// In ru, this message translates to:
  /// **'Гипертония 1'**
  String get bpLevelHtn1;

  /// No description provided for @bpLevelHtn2.
  ///
  /// In ru, this message translates to:
  /// **'Гипертония 2'**
  String get bpLevelHtn2;

  /// No description provided for @bpLevelCrisis.
  ///
  /// In ru, this message translates to:
  /// **'Кризис'**
  String get bpLevelCrisis;

  /// No description provided for @notifTitleMeasureNow.
  ///
  /// In ru, this message translates to:
  /// **'Пора измерить давление'**
  String get notifTitleMeasureNow;

  /// No description provided for @notifBodyDontForget.
  ///
  /// In ru, this message translates to:
  /// **'Не забудьте внести данные в дневник для контроля здоровья.'**
  String get notifBodyDontForget;

  /// No description provided for @notifChannelName.
  ///
  /// In ru, this message translates to:
  /// **'Напоминания о давлении'**
  String get notifChannelName;

  /// No description provided for @notifChannelDescription.
  ///
  /// In ru, this message translates to:
  /// **'Ежедневные уведомления о необходимости замера давления'**
  String get notifChannelDescription;

  /// No description provided for @profileAccount.
  ///
  /// In ru, this message translates to:
  /// **'Аккаунт'**
  String get profileAccount;

  /// No description provided for @profileConnect.
  ///
  /// In ru, this message translates to:
  /// **'Подключить'**
  String get profileConnect;

  /// No description provided for @profileNotSignedIn.
  ///
  /// In ru, this message translates to:
  /// **'Вы не вошли в аккаунт'**
  String get profileNotSignedIn;

  /// No description provided for @profileSignIn.
  ///
  /// In ru, this message translates to:
  /// **'Войти'**
  String get profileSignIn;

  /// No description provided for @profileLinked.
  ///
  /// In ru, this message translates to:
  /// **'Аккаунт подключен'**
  String get profileLinked;

  /// No description provided for @profileSignOut.
  ///
  /// In ru, this message translates to:
  /// **'Выйти'**
  String get profileSignOut;

  /// No description provided for @profileChooseSignIn.
  ///
  /// In ru, this message translates to:
  /// **'Выберите способ входа'**
  String get profileChooseSignIn;

  /// No description provided for @profileSystolicLabel.
  ///
  /// In ru, this message translates to:
  /// **'Верхнее'**
  String get profileSystolicLabel;

  /// No description provided for @profileDiastolicLabel.
  ///
  /// In ru, this message translates to:
  /// **'Нижнее'**
  String get profileDiastolicLabel;

  /// No description provided for @premiumRemoveAds.
  ///
  /// In ru, this message translates to:
  /// **'Убрать рекламу'**
  String get premiumRemoveAds;

  /// No description provided for @premiumSubtitleOneTime.
  ///
  /// In ru, this message translates to:
  /// **'Разовый платеж 2,99 € -  навсегда'**
  String get premiumSubtitleOneTime;

  /// No description provided for @dobLabel.
  ///
  /// In ru, this message translates to:
  /// **'Дата рождения'**
  String get dobLabel;

  /// No description provided for @genderShortMale.
  ///
  /// In ru, this message translates to:
  /// **'Муж.'**
  String get genderShortMale;

  /// No description provided for @genderShortFemale.
  ///
  /// In ru, this message translates to:
  /// **'Жен.'**
  String get genderShortFemale;

  /// No description provided for @appTitle.
  ///
  /// In ru, this message translates to:
  /// **'Дневник давления'**
  String get appTitle;

  /// No description provided for @yourCondition.
  ///
  /// In ru, this message translates to:
  /// **'Ваше состояние'**
  String get yourCondition;

  /// No description provided for @normalStatus.
  ///
  /// In ru, this message translates to:
  /// **'В норме'**
  String get normalStatus;

  /// No description provided for @history.
  ///
  /// In ru, this message translates to:
  /// **'История'**
  String get history;

  /// No description provided for @systolic.
  ///
  /// In ru, this message translates to:
  /// **'Верхнее'**
  String get systolic;

  /// No description provided for @diastolic.
  ///
  /// In ru, this message translates to:
  /// **'Нижнее'**
  String get diastolic;

  /// No description provided for @pulse.
  ///
  /// In ru, this message translates to:
  /// **'Пульс'**
  String get pulse;

  /// No description provided for @addRecord.
  ///
  /// In ru, this message translates to:
  /// **'Новая запись'**
  String get addRecord;

  /// No description provided for @save.
  ///
  /// In ru, this message translates to:
  /// **'Сохранить'**
  String get save;

  /// No description provided for @cancel.
  ///
  /// In ru, this message translates to:
  /// **'Отмена'**
  String get cancel;

  /// No description provided for @settings.
  ///
  /// In ru, this message translates to:
  /// **'Настройки'**
  String get settings;

  /// No description provided for @profile.
  ///
  /// In ru, this message translates to:
  /// **'Профиль'**
  String get profile;

  /// No description provided for @language.
  ///
  /// In ru, this message translates to:
  /// **'Язык'**
  String get language;

  /// No description provided for @theme.
  ///
  /// In ru, this message translates to:
  /// **'Тема'**
  String get theme;

  /// No description provided for @unitMmHg.
  ///
  /// In ru, this message translates to:
  /// **'мм рт. ст.'**
  String get unitMmHg;

  /// No description provided for @unitBpm.
  ///
  /// In ru, this message translates to:
  /// **'уд/мин'**
  String get unitBpm;

  /// No description provided for @noRecords.
  ///
  /// In ru, this message translates to:
  /// **'Записей пока нет'**
  String get noRecords;

  /// No description provided for @lastMeasurement.
  ///
  /// In ru, this message translates to:
  /// **'Последнее замер: {date}'**
  String lastMeasurement(String date);
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
