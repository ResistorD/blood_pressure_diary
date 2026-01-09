import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:blood_pressure_diary/l10n/generated/app_localizations.dart';
import 'package:blood_pressure_diary/core/theme/app_theme.dart';
import 'package:blood_pressure_diary/features/settings/data/models/settings_model.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_cubit.dart';
import 'package:blood_pressure_diary/features/settings/presentation/bloc/settings_state.dart';
import 'package:blood_pressure_diary/core/services/export_service.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context)!;

    return BlocListener<SettingsCubit, SettingsState>(
      listener: (context, state) {
        if (state.errorMessage != null) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(state.errorMessage!),
              backgroundColor: state.errorMessage!.contains('Ошибка') || state.errorMessage!.contains('error') 
                  ? Colors.red 
                  : Colors.orange,
            ),
          );
        }
      },
      child: BlocBuilder<SettingsCubit, SettingsState>(
        builder: (context, state) {
          return Scaffold(
            backgroundColor: AppUI.background,
            appBar: AppBar(
              title: Text(
                l10n.settings,
                style: const TextStyle(
                  color: Colors.black,
                  fontFamily: 'Inter',
                  fontWeight: FontWeight.bold,
                ),
              ),
              backgroundColor: Colors.white,
              elevation: 0,
              leading: IconButton(
                icon: const Icon(Icons.arrow_back, color: Colors.black),
                onPressed: () => Navigator.pop(context),
              ),
            ),
            body: Stack(
              children: [
                ListView(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 20),
                  children: [
                    _buildSectionTitle(l10n.theme),
                    _buildThemeSelector(context, state.settings.themeMode, l10n),
                    const Divider(),
                    SwitchListTile(
                      title: Text(
                        l10n.notifications,
                        style: const TextStyle(fontWeight: FontWeight.bold),
                      ),
                      value: state.settings.notificationsEnabled,
                      onChanged: (bool value) {
                        context.read<SettingsCubit>().toggleNotifications(value);
                      },
                      activeThumbColor: AppUI.headerBlue,
                      activeTrackColor: AppUI.headerBlue.withOpacity(0.5),
                    ),
                    _buildSectionTitle(l10n.reminders),
                    ...state.settings.reminders.asMap().entries.map((entry) {
                      return ListTile(
                        title: Text(entry.value),
                        trailing: IconButton(
                          icon: const Icon(Icons.delete_outline, color: Colors.red),
                          onPressed: () => context.read<SettingsCubit>().removeReminder(entry.key),
                        ),
                      );
                    }),
                    ListTile(
                      leading: const Icon(Icons.add),
                      title: Text(l10n.addReminder),
                      onTap: () async {
                        final time = await showTimePicker(
                          context: context,
                          initialTime: TimeOfDay.now(),
                        );
                        if (time != null && context.mounted) {
                          context.read<SettingsCubit>().addReminder(time);
                        }
                      },
                    ),
                    const Divider(),
                    _buildSectionTitle(l10n.export),
                    ListTile(
                      leading: const Icon(Icons.share_outlined),
                      title: Text(l10n.export),
                      onTap: state.isExporting ? null : () => _showExportBottomSheet(context, l10n),
                      trailing: state.isExporting ? const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)) : null,
                    ),
                    const Divider(),
                    _buildSectionTitle(l10n.contactSupport),
                    ListTile(
                      leading: const Icon(Icons.mail_outline),
                      title: Text(l10n.contactSupport),
                      onTap: () => context.read<SettingsCubit>().contactSupport(),
                    ),
                    ListTile(
                      leading: const Icon(Icons.star_outline),
                      title: Text(l10n.rateApp),
                      onTap: () => context.read<SettingsCubit>().rateApp(),
                    ),
                    const Divider(),
                    ListTile(
                      leading: const Icon(Icons.delete_forever, color: Colors.red),
                      title: Text(
                        l10n.clearData,
                        style: const TextStyle(color: Colors.red),
                      ),
                      onTap: () => _showClearDataDialog(context, l10n),
                    ),
                    const SizedBox(height: 40),
                    Center(
                      child: Text(
                        l10n.version('1.0.0'),
                        style: TextStyle(color: Colors.grey[600], fontSize: 14),
                      ),
                    ),
                  ],
                ),
                if (state.isExporting)
                  Container(
                    color: Colors.black.withOpacity(0.1),
                    child: const Center(
                      child: CircularProgressIndicator(),
                    ),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
      child: Text(
        title,
        style: const TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.bold,
          color: AppUI.headerBlue,
        ),
      ),
    );
  }

  Widget _buildThemeSelector(BuildContext context, AppThemeMode currentMode, AppLocalizations l10n) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: SegmentedButton<AppThemeMode>(
        segments: [
          ButtonSegment(value: AppThemeMode.light, label: Text(l10n.light)),
          ButtonSegment(value: AppThemeMode.dark, label: Text(l10n.dark)),
          ButtonSegment(value: AppThemeMode.system, label: Text(l10n.system)),
        ],
        selected: {currentMode},
        onSelectionChanged: (Set<AppThemeMode> newSelection) {
          context.read<SettingsCubit>().setThemeMode(newSelection.first);
        },
      ),
    );
  }

  void _showExportBottomSheet(BuildContext context, AppLocalizations l10n) {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Padding(
              padding: const EdgeInsets.all(16.0),
              child: Text(
                l10n.export,
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
            ),
            ListTile(
              leading: const Icon(Icons.picture_as_pdf_outlined, color: AppUI.accentRed),
              title: Text(l10n.exportPDF),
              onTap: () {
                Navigator.pop(context);
                context.read<SettingsCubit>().exportData(ExportFormat.pdf);
              },
            ),
            ListTile(
              leading: const Icon(Icons.description_outlined, color: Colors.green),
              title: Text(l10n.exportCSV),
              onTap: () {
                Navigator.pop(context);
                context.read<SettingsCubit>().exportData(ExportFormat.csv);
              },
            ),
            const SizedBox(height: 8),
          ],
        ),
      ),
    );
  }

  void _showClearDataDialog(BuildContext context, AppLocalizations l10n) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(l10n.clearData),
        content: Text(l10n.clearDataConfirm),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(l10n.no),
          ),
          TextButton(
            onPressed: () {
              context.read<SettingsCubit>().clearAllData();
              Navigator.pop(ctx);
            },
            child: Text(
              l10n.yes,
              style: const TextStyle(color: Colors.red),
            ),
          ),
        ],
      ),
    );
  }
}
