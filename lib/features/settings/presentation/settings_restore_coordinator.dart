class SettingsRestoreCoordinator {
  const SettingsRestoreCoordinator();

  Future<void> restoreAndRefresh({
    required Future<void> Function() restoreBackup,
    required Future<void> Function() reloadSettings,
    required Future<void> Function({required bool force}) loadProfile,
  }) async {
    await restoreBackup();
    await reloadSettings();
    await loadProfile(force: true);
  }
}
