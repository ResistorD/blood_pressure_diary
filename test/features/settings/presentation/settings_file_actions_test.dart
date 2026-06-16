import 'dart:io';

import 'package:blood_pressure_diary/features/settings/presentation/settings_file_actions.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('picker cancel returns null for backup json', () async {
    final actions = SettingsFileActions.test(
      pickBackupJsonPath: () async => null,
    );

    await expectLater(actions.pickBackupJsonPath(), completion(isNull));
  });

  test('restore file read error becomes SettingsFileActionException', () async {
    final actions = SettingsFileActions.test(
      readFileText: (_) async => throw const FileSystemException('read failed'),
    );

    await expectLater(
      actions.restoreBackupFromPath('backup.json'),
      throwsA(isA<SettingsFileActionException>()),
    );
  });

  test('share error becomes SettingsFileActionException', () async {
    final actions = SettingsFileActions.test(
      temporaryDirectoryPath: () async => '/tmp',
      writeFileText: (_, _) async {},
      shareFile: (_, _) async => throw StateError('share failed'),
    );

    await expectLater(
      actions.shareBackupJson(shareText: 'backup'),
      throwsA(isA<SettingsFileActionException>()),
    );
  });

  test('csv parse error becomes SettingsFileActionException', () async {
    final actions = SettingsFileActions.test(
      pickCsvPath: () async => 'bad.csv',
      readFileText: (_) async => 'not,a,known,csv\n1,2,3,4',
    );

    await expectLater(
      actions.pickAndParseCsv(),
      throwsA(isA<SettingsFileActionException>()),
    );
  });
}
