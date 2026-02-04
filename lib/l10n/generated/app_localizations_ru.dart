// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Russian (`ru`).
class AppLocalizationsRu extends AppLocalizations {
  AppLocalizationsRu([String locale = 'ru']) : super(locale);

  @override
  String get settings => 'Настройки';

  @override
  String get selectLanguage => 'Выбор языка';

  @override
  String get appTitle => 'Дневник давления';

  @override
  String get notifications => 'Уведомления';

  @override
  String get clearData => 'Очистить данные';

  @override
  String get aboutApp => 'О приложении';

  @override
  String version(String version) {
    return 'Версия $version';
  }

  @override
  String get functionInDevelopment => 'Функция в разработке';

  @override
  String get deleteRecordQ => 'Удалить запись?';

  @override
  String get cannotUndo => 'Это действие нельзя отменить.';

  @override
  String get cancel => 'Отмена';

  @override
  String get delete => 'Удалить';

  @override
  String get theme => 'Тема';

  @override
  String get language => 'Язык';

  @override
  String get light => 'Светлая';

  @override
  String get dark => 'Темная';

  @override
  String get system => 'Системная';

  @override
  String get reminders => 'Напоминания';

  @override
  String get addReminder => 'Добавить время';

  @override
  String get clearDataConfirm =>
      'Вы уверены, что хотите удалить все записи? Это действие нельзя отменить.';

  @override
  String get yes => 'Да';

  @override
  String get no => 'Нет';

  @override
  String get export => 'Экспорт данных';

  @override
  String get exportCSV => 'CSV Таблица';

  @override
  String get exportPDF => 'PDF Отчет';

  @override
  String get contactSupport => 'Написать нам';

  @override
  String get rateApp => 'Оценить приложение';

  @override
  String get supportEmail => 'your_email@mail.com';

  @override
  String get profile => 'Профиль';

  @override
  String get name => 'Имя';

  @override
  String get age => 'Возраст';

  @override
  String get gender => 'Пол';

  @override
  String get weight => 'Вес';

  @override
  String get male => 'Мужской';

  @override
  String get female => 'Женский';

  @override
  String get other => 'Другой';

  @override
  String get myGoal => 'Моя цель';

  @override
  String get targetPressure => 'Целевое давление';

  @override
  String get systolic => 'Систолическое';

  @override
  String get diastolic => 'Диастолическое';

  @override
  String get premium => 'Премиум';

  @override
  String get oneTimePayment => 'Разовый платеж 2,99 €';

  @override
  String get buyPremium => 'Купить Премиум';

  @override
  String get save => 'Сохранить';
}
