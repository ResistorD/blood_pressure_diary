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
  String get today => 'Сегодня';

  @override
  String get week => 'Неделя';

  @override
  String get month => 'Месяц';

  @override
  String get allShort => 'Все';

  @override
  String get allTime => 'Всё время';

  @override
  String get myDiary => 'Мой дневник';

  @override
  String recordsOne(Object count) {
    return 'запись';
  }

  @override
  String recordsFew(Object count) {
    return 'записи';
  }

  @override
  String recordsMany(Object count) {
    return 'записей';
  }

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

  @override
  String get pickTime => 'Выберите время';

  @override
  String get pickDate => 'Выберите дату';

  @override
  String get deleteRecordQ => 'Удалить запись?';

  @override
  String get cannotUndo => 'Это действие нельзя отменить.';

  @override
  String get delete => 'Удалить';

  @override
  String get commentHint => 'Комментарий';

  @override
  String get newRecord => 'Новая запись';

  @override
  String get systolicShort => 'Сист.';

  @override
  String get diastolicShort => 'Диаст.';

  @override
  String get reminders => 'Напоминания';

  @override
  String get addReminder => 'Добавить напоминание';

  @override
  String get clearData => 'Очистить данные';

  @override
  String get clearDataConfirm => 'Точно очистить все данные?';

  @override
  String get export => 'Экспорт';

  @override
  String get exportCSV => 'Экспорт в CSV';

  @override
  String get exportPDF => 'Экспорт в PDF';

  @override
  String get contactSupport => 'Написать нам';

  @override
  String get rateApp => 'Оценить приложение';

  @override
  String get versionLabel => 'Версия';

  @override
  String get yes => 'Да';

  @override
  String get no => 'Нет';

  @override
  String get light => 'Светлая';

  @override
  String get dark => 'Тёмная';

  @override
  String get system => 'Системная';

  @override
  String get privacyPolicy => 'Политика конфиденциальности';

  @override
  String get privacyPolicyLastUpdate => 'Обновлено:';

  @override
  String get privacyPolicyFullText =>
      'Мы уважаем вашу конфиденциальность.\n\nКакие данные хранит приложение\n• Записи артериального давления (верхнее/нижнее), пульс, дата/время.\n• Необязательные комментарии и теги.\n• Настройки (язык, тема, напоминания).\n\nГде хранятся данные\n• По умолчанию все данные хранятся локально на вашем устройстве.\n\nНапоминания\n• Если вы включаете напоминания, приложение планирует локальные уведомления на устройстве.\n• Приложение не передаёт ваши измерения на сервер, чтобы запускать напоминания.\n\nРезервные копии и экспорт\n• При создании резервной копии (JSON) или экспорта (PDF/CSV) приложение формирует файл на вашем устройстве.\n• Если вы делитесь этим файлом через другие приложения, эти приложения обрабатывают данные согласно своим политикам конфиденциальности.\n\nАналитика и реклама\n• Приложение не продаёт ваши персональные данные намеренно.\n• Если используются сторонние сервисы (например, провайдеры входа или биллинг магазина), они могут обрабатывать ограниченную техническую информацию, необходимую для предоставления сервиса.\n\nВаш выбор\n• Вы можете удалять записи и очистить все данные приложения внутри приложения.\n• Вы можете отключить напоминания в любой момент.\n\nКонтакты\n• Если вы обращаетесь в поддержку, информация, которую вы отправляете (содержимое письма), обрабатывается вашим почтовым провайдером.\n\nЭтот текст предоставлен в информационных целях и может обновляться по мере развития приложения.';

  @override
  String get averageLabel => 'Среднее:';

  @override
  String get minLabel => 'Мин.:';

  @override
  String get maxLabel => 'Макс.:';

  @override
  String get pressureLabel => 'Давление';

  @override
  String get restoreBackupTitle => 'Восстановление из копии';

  @override
  String get restoreBackupConfirm =>
      'Это действие заменит все текущие данные приложения (профиль, настройки и записи давления). Продолжить?';

  @override
  String get restore => 'Восстановить';

  @override
  String get dataRestored => 'Данные восстановлены';

  @override
  String get morning => 'Утро';

  @override
  String get evening => 'Вечер';

  @override
  String get aboutApp => 'О приложении';

  @override
  String get appAboutText =>
      'Pressure Diary — дневник измерений давления и пульса. Данные вводятся пользователем и могут быть полезны для наблюдения динамики.';

  @override
  String get version => 'Версия';

  @override
  String get supportProject => 'Поддержать проект';

  @override
  String get supportProjectHint => 'Добровольная благодарность разработчику';

  @override
  String get emailClientNotFound => 'Не найдено приложение для отправки почты';

  @override
  String get actionFailed => 'Не удалось выполнить действие';

  @override
  String get time => 'Время';

  @override
  String get supportProjectText =>
      'Если приложение оказалось полезным — можно символически поддержать разработку. Это не подписка и не обязательство. Даже просто поделиться приложением — уже помощь 🙂';

  @override
  String get supportCoffee => '€2 — кофе';

  @override
  String get supportCoffeeHint => 'Символическая благодарность';

  @override
  String get supportPizza => '€3 — пицца';

  @override
  String get supportPizzaHint => 'Чуть щедрее, всё ещё по-человечески';

  @override
  String get supportBurger => '€5 — бургер';

  @override
  String get supportBurgerHint => 'Максимальный уровень гражданской доблести';

  @override
  String get shareApp => 'Поделиться приложением';

  @override
  String get shareAppHint => 'Отправить ссылку друзьям';

  @override
  String get shareAppText => 'Ссылка на приложение:';

  @override
  String get russian => 'Русский';

  @override
  String get account => 'Аккаунт';

  @override
  String get accountConnected => 'Аккаунт подключен';

  @override
  String get accountNotConnected => 'Вы не вошли в аккаунт';

  @override
  String get chooseSignIn => 'Выберите способ входа';

  @override
  String get connect => 'Подключить';

  @override
  String get signIn => 'Войти';

  @override
  String get signOut => 'Выйти';

  @override
  String get name => 'Имя';

  @override
  String get gender => 'Пол';

  @override
  String get maleShort => 'Муж.';

  @override
  String get femaleShort => 'Жен.';

  @override
  String get birthDate => 'Дата рождения';

  @override
  String get pressureNorms => 'Нормы давления';

  @override
  String get upper => 'Верхнее';

  @override
  String get lower => 'Нижнее';

  @override
  String get removeAds => 'Убрать рекламу';

  @override
  String get removeAdsSubtitle => 'Разовый платеж 2,99 € — навсегда';

  @override
  String get bpm => 'уд/мин';

  @override
  String get accountLinked => 'Аккаунт подключен';

  @override
  String get notSignedIn => 'Вы не вошли в аккаунт';

  @override
  String get link => 'Подключить';

  @override
  String get buyPremium => 'Убрать рекламу';

  @override
  String get oneTimePayment => 'Разовый платеж 2,99 € — навсегда';

  @override
  String get male => 'Муж.';

  @override
  String get female => 'Жен.';
}
