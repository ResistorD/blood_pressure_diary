import 'package:isar/isar.dart';

part 'user_profile.g.dart';

@collection
class UserProfile {
  Id id = 0; // Всегда 0 для единственной записи профиля

  String name = '';
  int age = 0;
  String gender = 'male'; // 'male', 'female', 'other'
  double weight = 0.0;

  int targetSystolic = 120;
  int targetDiastolic = 80;

  // --- Account link (локальная привязка, реальная: хранится в Isar)
  bool accountLinked = false;
  String accountEmail = '';
  String accountProvider = ''; // 'email' | 'google' | 'apple'

  UserProfile({
    this.name = '',
    this.age = 0,
    this.gender = 'male',
    this.weight = 0.0,
    this.targetSystolic = 120,
    this.targetDiastolic = 80,
    this.accountLinked = false,
    this.accountEmail = '',
    this.accountProvider = '',
  });
}
