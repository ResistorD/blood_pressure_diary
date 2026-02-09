// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Russian (`ru`).
class AppLocalizationsRu extends AppLocalizations {
  AppLocalizationsRu([String locale = 'ru']) : super(locale);

  @override
  String get backupJson => 'Резервная копия (JSON)';

  @override
  String get restoreFromBackup => 'Восстановить из копии';

  @override
  String get restoreDialogTitle => 'Восстановление из копии';

  @override
  String get restoreDialogBody =>
      'Это действие заменит все текущие данные приложения (профиль, настройки и записи давления). Продолжить?';

  @override
  String get restoreAction => 'Восстановить';

  @override
  String get dataRestoredSnack => 'Данные восстановлены';

  @override
  String get reminderMorning => 'Утро';

  @override
  String get reminderEvening => 'Вечер';

  @override
  String get reminderTime => 'Время';

  @override
  String get languageRu => 'Русский';

  @override
  String get languageEn => 'English';

  @override
  String get noRecordsForPeriod => 'Нет записей за выбранный период';

  @override
  String get noDataForPeriod => 'Нет данных за этот период';

  @override
  String get noData => 'Нет данных';

  @override
  String get chartsTitle => 'Графики';

  @override
  String get tabPressure => 'Давление';

  @override
  String get tabPulse => 'Пульс';

  @override
  String get periodWeek => 'Неделя';

  @override
  String get periodMonth => 'Месяц';

  @override
  String get periodAll => 'Все';

  @override
  String get avgLabel => 'Среднее:';

  @override
  String get maxLabelShort => 'Макс.:';

  @override
  String get minLabelShort => 'Мин.:';

  @override
  String get bpmUnit => 'уд/мин';

  @override
  String get tagHeader => 'Теги';

  @override
  String tagHeaderWithCount(int count) {
    return 'Теги ($count)';
  }

  @override
  String get tagAfterCoffee => 'После кофе';

  @override
  String get tagAlcohol => 'Алкоголь';

  @override
  String get tagAfterMeal => 'После еды';

  @override
  String get tagAfterWalk => 'После прогулки';

  @override
  String get tagAfterTraining => 'После тренировки';

  @override
  String get tagStress => 'Стресс';

  @override
  String get tagBadSleep => 'Плохой сон';

  @override
  String get tagHeadache => 'Головная боль';

  @override
  String get tagTookMeds => 'Принял лекарство';

  @override
  String get tagMissedDose => 'Пропустил приём';

  @override
  String get bpLevelLow => 'Понижено';

  @override
  String get bpLevelNormal => 'Норма';

  @override
  String get bpLevelElevated => 'Повышено';

  @override
  String get bpLevelHtn1 => 'Гипертония 1';

  @override
  String get bpLevelHtn2 => 'Гипертония 2';

  @override
  String get bpLevelCrisis => 'Кризис';

  @override
  String get notifTitleMeasureNow => 'Пора измерить давление';

  @override
  String get notifBodyDontForget =>
      'Не забудьте внести данные в дневник для контроля здоровья.';

  @override
  String get notifChannelName => 'Напоминания о давлении';

  @override
  String get notifChannelDescription =>
      'Ежедневные уведомления о необходимости замера давления';

  @override
  String get profileAccount => 'Аккаунт';

  @override
  String get profileConnect => 'Подключить';

  @override
  String get profileNotSignedIn => 'Вы не вошли в аккаунт';

  @override
  String get profileSignIn => 'Войти';

  @override
  String get profileLinked => 'Аккаунт подключен';

  @override
  String get profileSignOut => 'Выйти';

  @override
  String get profileChooseSignIn => 'Выберите способ входа';

  @override
  String get profileSystolicLabel => 'Верхнее';

  @override
  String get profileDiastolicLabel => 'Нижнее';

  @override
  String get premiumRemoveAds => 'Убрать рекламу';

  @override
  String get premiumSubtitleOneTime => 'Разовый платеж 2,99 € -  навсегда';

  @override
  String get dobLabel => 'Дата рождения';

  @override
  String get genderShortMale => 'Муж.';

  @override
  String get genderShortFemale => 'Жен.';

  @override
  String get appTitle => 'Дневник давления';

  @override
  String get yourCondition => 'Ваше состояние';

  @override
  String get normalStatus => 'В норме';

  @override
  String get history => 'История';

  @override
  String get systolic => 'Верхнее';

  @override
  String get diastolic => 'Нижнее';

  @override
  String get pulse => 'Пульс';

  @override
  String get addRecord => 'Новая запись';

  @override
  String get save => 'Сохранить';

  @override
  String get cancel => 'Отмена';

  @override
  String get settings => 'Настройки';

  @override
  String get profile => 'Профиль';

  @override
  String get language => 'Язык';

  @override
  String get theme => 'Тема';

  @override
  String get unitMmHg => 'мм рт. ст.';

  @override
  String get unitBpm => 'уд/мин';

  @override
  String get noRecords => 'Записей пока нет';

  @override
  String lastMeasurement(String date) {
    return 'Последнее замер: $date';
  }
}
