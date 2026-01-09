class AppStrings {
  static const newRecord = 'Новая запись';
  static const deleteRecordQ = 'Удалить запись?';
  static const cannotUndo = 'Это действие нельзя отменить.';
  static const cancel = 'Отмена';
  static const delete = 'Удалить';
  static const pickTime = 'Выберите время';
  static const pickDate = 'Выберите дату';
  static const systolicShort = 'Сист.';
  static const diastolicShort = 'Диаст.';
  static const pulse = 'Пульс';
  static const commentHint = 'Комментарий';
  static const save = 'Сохранить';
  static const today = 'Сегодня';
  static const week = 'Неделя';
  static const month = 'Месяц';
  static const allShort = 'Всё';
  static const allTime = 'Всё время';
  static const myDiary = 'Мой дневник';
  static String recordsWord(int n) {
    final nAbs = n.abs() % 100;
    final n1 = nAbs % 10;
    if (nAbs >= 11 && nAbs <= 19) return 'записей';
    if (n1 == 1) return 'запись';
    if (n1 >= 2 && n1 <= 4) return 'записи';
    return 'записей';
  }
}
