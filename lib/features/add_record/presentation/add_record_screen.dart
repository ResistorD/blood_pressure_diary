import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:get_it/get_it.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:flutter/services.dart';

import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/theme/scale.dart';
import '../../../core/utils/input_field.dart';
import 'bloc/add_record_bloc.dart';
import 'bloc/add_record_event.dart';
import 'bloc/add_record_state.dart';
import 'widgets/custom_keypad.dart';

String _tr(BuildContext context, {required String ru, required String en}) {
  final code = Localizations.localeOf(context).languageCode.toLowerCase();
  return code == 'ru' ? ru : en;
}

class TagPreset {
  /// Значение, которое сохраняем в запись (стабильное, не зависит от языка).
  final String value;

  /// Текст, который показываем пользователю (может зависеть от языка).
  final String ruLabel;
  final String enLabel;

  final String iconAsset;

  const TagPreset(this.value, this.iconAsset, {required this.ruLabel, required this.enLabel});

  String label(BuildContext context) => _tr(context, ru: ruLabel, en: enLabel);
}

class AddRecordScreen extends StatelessWidget {
  static const List<TagPreset> presetTags = [
    TagPreset('После кофе', 'assets/icons/tags/coffee.svg', ruLabel: 'После кофе', enLabel: 'After coffee'),
    TagPreset('Алкоголь', 'assets/icons/tags/alcohol.svg', ruLabel: 'Алкоголь', enLabel: 'Alcohol'),
    TagPreset('После еды', 'assets/icons/tags/hamburger.svg', ruLabel: 'После еды', enLabel: 'After meal'),
    TagPreset('После прогулки', 'assets/icons/tags/walk.svg', ruLabel: 'После прогулки', enLabel: 'After walk'),
    TagPreset('После тренировки', 'assets/icons/tags/training.svg', ruLabel: 'После тренировки', enLabel: 'After workout'),
    TagPreset('Стресс', 'assets/icons/tags/stress.svg', ruLabel: 'Стресс', enLabel: 'Stress'),
    TagPreset('Плохой сон', 'assets/icons/tags/sleep.svg', ruLabel: 'Плохой сон', enLabel: 'Poor sleep'),
    TagPreset('Головная боль', 'assets/icons/tags/headache.svg', ruLabel: 'Головная боль', enLabel: 'Headache'),
    TagPreset('Принял лекарство', 'assets/icons/tags/meds.svg', ruLabel: 'Принял лекарство', enLabel: 'Took meds'),
    TagPreset('Пропустил приём', 'assets/icons/tags/missed_meds.svg', ruLabel: 'Пропустил приём', enLabel: 'Missed meds'),
  ];

  final BloodPressureRecord? record;

  const AddRecordScreen({super.key, this.record});

  @override
  Widget build(BuildContext context) {
    return BlocProvider(
      create: (_) {
        final bloc = GetIt.I<AddRecordBloc>();
        if (record != null) {
          bloc.add(EditStarted(record!));
        }
        return bloc;
      },
      child: _AddRecordView(isEditing: record != null),
    );
  }
}

class _AddRecordView extends StatefulWidget {
  final bool isEditing;

  const _AddRecordView({required this.isEditing});

  @override
  State<_AddRecordView> createState() => _AddRecordViewState();
}

class _AddRecordViewState extends State<_AddRecordView> {
  final TextEditingController _noteController = TextEditingController();
  final FocusNode _noteFocusNode = FocusNode();
  Timer? _draftDebounce;
  bool _draftLoaded = false;

  @override
  void initState() {
    super.initState();
    // ВАЖНО: при фокусе на комментарии отключаем кастомный keypad,
    // чтобы не было "цифровая под стандартной".
    _noteFocusNode.addListener(() {
      if (_noteFocusNode.hasFocus) {
        _haptic();
        context.read<AddRecordBloc>().add(const FieldChanged(InputField.none));
      }
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadDraftIfNeeded();
    });
  }

  @override
  void dispose() {
    _draftDebounce?.cancel();
    _noteController.dispose();
    _noteFocusNode.dispose();
    super.dispose();
  }

  void _haptic() {
    HapticFeedback.selectionClick();
  }

  Future<File> _draftFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/add_record_draft.json');
  }

  bool _hasDraftContent(AddRecordState s) {
    return s.systolic.trim().isNotEmpty ||
        s.diastolic.trim().isNotEmpty ||
        s.pulse.trim().isNotEmpty ||
        s.note.trim().isNotEmpty ||
        s.tags.isNotEmpty;
  }

  void _scheduleDraftSave(AddRecordState s) {
    if (!_draftLoaded || widget.isEditing) return;
    _draftDebounce?.cancel();
    _draftDebounce = Timer(const Duration(milliseconds: 400), () {
      _saveDraft(s);
    });
  }

  Future<void> _saveDraft(AddRecordState s) async {
    if (widget.isEditing) return;
    final file = await _draftFile();
    if (!_hasDraftContent(s)) {
      if (await file.exists()) {
        await file.delete();
      }
      return;
    }

    final payload = <String, dynamic>{
      'systolic': s.systolic,
      'diastolic': s.diastolic,
      'pulse': s.pulse,
      'note': s.note,
      'selectedDateTime': s.selectedDateTime.toIso8601String(),
      'tags': s.tags,
    };
    await file.writeAsString(jsonEncode(payload), flush: true);
  }

  Future<void> _clearDraft() async {
    final file = await _draftFile();
    if (await file.exists()) {
      await file.delete();
    }
  }

  Future<File> _commentTemplatesFile() async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/comment_templates.json');
  }

  Future<List<String>> _loadCommentTemplates() async {
    final file = await _commentTemplatesFile();
    if (!await file.exists()) return <String>[];

    try {
      final raw = await file.readAsString();
      final data = jsonDecode(raw);
      if (data is! List) return <String>[];

      return data
          .map((e) => e.toString().trim())
          .where((e) => e.isNotEmpty)
          .toSet()
          .toList();
    } catch (_) {
      return <String>[];
    }
  }

  Future<void> _saveCommentTemplates(List<String> templates) async {
    final file = await _commentTemplatesFile();
    final clean = templates
        .map((e) => e.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList();

    await file.writeAsString(jsonEncode(clean), flush: true);
  }

  Future<void> _openCommentTemplatesSheet(BuildContext context, String currentNote) async {
    _haptic();

    final templates = await _loadCommentTemplates();
    if (!context.mounted) return;

    final selected = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (sheetContext) {
        return StatefulBuilder(
          builder: (sheetContext, setSheetState) {
            final colors = context.appColors;
            final space = context.appSpace;
            final radii = context.appRadii;
            final txt = context.appText;
            final isDark = Theme.of(context).brightness == Brightness.dark;

            final note = currentNote.trim();
            final canAdd = note.isNotEmpty && !templates.contains(note);

            final bg = isDark ? AppPalette.dark800 : colors.surface;
            final itemBg = isDark ? AppPalette.dark700 : colors.background;
            final titleStyle = TextStyle(
              fontFamily: txt.family,
              fontSize: sp(context, txt.fs18),
              fontWeight: txt.w700,
              color: colors.textPrimary,
              height: 1.0,
            );
            final itemStyle = TextStyle(
              fontFamily: txt.family,
              fontSize: sp(context, txt.fs16),
              fontWeight: txt.w500,
              color: colors.textPrimary,
              height: 1.0,
            );
            final hintStyle = TextStyle(
              fontFamily: txt.family,
              fontSize: sp(context, txt.fs14),
              fontWeight: txt.w400,
              color: isDark ? AppPalette.dark350 : AppPalette.grey500,
              height: 1.2,
            );

            return SafeArea(
              child: Container(
                decoration: BoxDecoration(
                  color: bg,
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(dp(context, radii.r10)),
                    topRight: Radius.circular(dp(context, radii.r10)),
                  ),
                ),
                padding: EdgeInsets.fromLTRB(
                  dp(context, space.s16),
                  dp(context, space.s16),
                  dp(context, space.s16),
                  dp(context, space.s16),
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      _tr(context, ru: 'Шаблоны комментариев', en: 'Comment templates'),
                      style: titleStyle,
                    ),
                    SizedBox(height: dp(context, space.s12)),
                    if (canAdd) ...[
                      GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: () async {
                          templates.add(note);
                          await _saveCommentTemplates(templates);
                          setSheetState(() {});
                        },
                        child: Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: dp(context, space.s12),
                            vertical: dp(context, space.s12),
                          ),
                          decoration: BoxDecoration(
                            color: itemBg,
                            borderRadius: BorderRadius.circular(dp(context, radii.r10)),
                          ),
                          child: Text(
                            _tr(context, ru: '+ Добавить текущий комментарий', en: '+ Add current comment'),
                            style: itemStyle,
                          ),
                        ),
                      ),
                      SizedBox(height: dp(context, space.s12)),
                    ],
                    if (templates.isEmpty)
                      Text(
                        _tr(
                          context,
                          ru: 'Шаблонов пока нет. Введите комментарий и добавьте его здесь.',
                          en: 'No templates yet. Enter a comment and add it here.',
                        ),
                        style: hintStyle,
                      )
                    else
                      Flexible(
                        child: ListView.separated(
                          shrinkWrap: true,
                          itemCount: templates.length,
                          separatorBuilder: (_, __) => SizedBox(height: dp(context, space.s8)),
                          itemBuilder: (_, i) {
                            final template = templates[i];
                            return Container(
                              decoration: BoxDecoration(
                                color: itemBg,
                                borderRadius: BorderRadius.circular(dp(context, radii.r10)),
                              ),
                              child: Row(
                                children: [
                                  Expanded(
                                    child: GestureDetector(
                                      behavior: HitTestBehavior.opaque,
                                      onTap: () => Navigator.of(sheetContext).pop(template),
                                      child: Padding(
                                        padding: EdgeInsets.symmetric(
                                          horizontal: dp(context, space.s12),
                                          vertical: dp(context, space.s12),
                                        ),
                                        child: Text(
                                          template,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                          style: itemStyle,
                                        ),
                                      ),
                                    ),
                                  ),
                                  IconButton(
                                    icon: Icon(
                                      Icons.close,
                                      size: dp(context, space.s20),
                                      color: isDark ? AppPalette.dark350 : AppPalette.grey500,
                                    ),
                                    onPressed: () async {
                                      templates.removeAt(i);
                                      await _saveCommentTemplates(templates);
                                      setSheetState(() {});
                                    },
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                      ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );

    if (selected == null || !context.mounted) return;
    context.read<AddRecordBloc>().add(NoteChanged(selected));
  }

  Future<void> _loadDraftIfNeeded() async {
    if (widget.isEditing) {
      _draftLoaded = true;
      return;
    }

    try {
      final file = await _draftFile();
      if (!await file.exists()) {
        _draftLoaded = true;
        return;
      }
      final raw = await file.readAsString();
      final data = jsonDecode(raw);
      if (data is! Map) {
        await file.delete();
        _draftLoaded = true;
        return;
      }
      final systolic = (data['systolic'] ?? '').toString();
      final diastolic = (data['diastolic'] ?? '').toString();
      final pulse = (data['pulse'] ?? '').toString();
      final note = (data['note'] ?? '').toString();
      final dtRaw = (data['selectedDateTime'] ?? '').toString();
      final tagsRaw = data['tags'];

      final dt = DateTime.tryParse(dtRaw) ?? DateTime.now();
      final tags = tagsRaw is List ? tagsRaw.map((e) => e.toString()).toList() : <String>[];

      if (!mounted) return;
      context.read<AddRecordBloc>().add(DraftLoaded(
        systolic: systolic,
        diastolic: diastolic,
        pulse: pulse,
        note: note,
        selectedDateTime: dt,
        tags: tags,
      ));
    } catch (_) {
      // игнорируем ошибки чтения черновика
    } finally {
      _draftLoaded = true;
    }
  }

  String? _validationHint(AddRecordState s, bool isRu) {
    // Минимальный «почему нельзя сохранить», чтобы кнопка не выглядела сломанной.
    final touched = s.systolic.trim().isNotEmpty || s.diastolic.trim().isNotEmpty || s.pulse.trim().isNotEmpty;
    if (!touched || s.isValid) return null;

    final sys = int.tryParse(s.systolic.trim());
    final dia = int.tryParse(s.diastolic.trim());
    final pul = int.tryParse(s.pulse.trim());

    if (sys == null) return isRu ? 'Введите SYS (60–300)' : 'Enter SYS (60–300)';
    if (sys < 60 || sys > 300) return isRu ? 'SYS вне диапазона 60–300' : 'SYS is out of 60–300';

    // ВАЖНО: DIA проверяем раньше пульса — соответствует потоку ввода (SYS → DIA → Pulse).
    if (dia == null) return isRu ? 'Введите DIA (40–200)' : 'Enter DIA (40–200)';
    if (dia < 40 || dia > 200) return isRu ? 'DIA вне диапазона 40–200' : 'DIA is out of 40–200';
    if (dia >= sys) return isRu ? 'DIA должно быть меньше SYS' : 'DIA must be lower than SYS';

    if (pul == null) return isRu ? 'Введите пульс (30–250)' : 'Enter pulse (30–250)';
    if (pul < 30 || pul > 250) return isRu ? 'Пульс вне диапазона 30–250' : 'Pulse is out of 30–250';

    return isRu ? 'Проверь значения' : 'Check values';
  }

  Future<void> _pickTime(BuildContext context, DateTime current) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
      helpText: _tr(context, ru: 'Выберите время', en: 'Select time'),
    );
    if (picked == null || !context.mounted) return;

    final merged = DateTime(current.year, current.month, current.day, picked.hour, picked.minute);
    context.read<AddRecordBloc>().add(DateTimeSet(merged));
  }

  Future<void> _pickDate(BuildContext context, DateTime current) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(current.year - 1),
      lastDate: DateTime(current.year + 1),
      helpText: _tr(context, ru: 'Выберите дату', en: 'Select date'),
    );
    if (picked == null || !context.mounted) return;

    final merged = DateTime(picked.year, picked.month, picked.day, current.hour, current.minute);
    context.read<AddRecordBloc>().add(DateTimeSet(merged));
  }

  Future<void> _confirmDelete(BuildContext context) async {
    final colors = context.appColors;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(_tr(context, ru: 'Удалить запись?', en: 'Delete record?')),
        content: Text(_tr(context, ru: 'Отменить нельзя', en: 'This can’t be undone')),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(_tr(context, ru: 'Отмена', en: 'Cancel'), style: TextStyle(color: colors.brandStrong)),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(_tr(context, ru: 'Удалить', en: 'Delete'), style: TextStyle(color: colors.danger)),
          ),
        ],
      ),
    );

    if (ok == true && context.mounted) {
      context.read<AddRecordBloc>().add(DeleteSubmitted());
    }
  }

  double _bottomInset(BuildContext context) {
    final space = context.appSpace;

    // Bottom bar in AppNavigation: barH (69) + lift (43) ≈ 112.
    final barH = dp(context, space.s72 - space.s2 - space.s1);
    final outer = dp(context, space.s80 + space.s6);
    final lift = outer / 2;

    return barH + lift;
  }

  Widget _threeColGridSpan23({
    required BuildContext context,
    required double gap,
    required Widget col1,
    required Widget span23,
  }) {
    return LayoutBuilder(
      builder: (ctx, c) {
        final w = c.maxWidth;
        final colW = (w - 2 * gap) / 3;
        final spanW = colW * 2 + gap;

        return Row(
          children: [
            SizedBox(width: colW, child: col1),
            SizedBox(width: gap),
            SizedBox(width: spanW, child: span23),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final shadows = context.appShadow;
    final txt = context.appText;

    final isDark = Theme.of(context).brightness == Brightness.dark;

    // фиксированный внешний горизонтальный паддинг (эталон)
    final side = dp(context, space.s20);

    final topInset = MediaQuery.paddingOf(context).top;
    final headerH = dp(context, space.s128);

    final pillH = dp(context, space.s48);
    final pillR = dp(context, radii.r10);

    final commentH = dp(context, space.s72);

    final gap20 = dp(context, space.s20);
    final gap16 = dp(context, space.s16);

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final surface = isDark ? AppPalette.dark700 : colors.surface;

    final screenH = MediaQuery.sizeOf(context).height;
    final isSmallScreen = screenH < 700;
    final keypadCellH = isSmallScreen ? (pillH - dp(context, space.s6)) : pillH;
    final keypadGap = isSmallScreen ? dp(context, space.s12) : dp(context, space.s16);
    final keypadBg = isDark ? AppPalette.dark800 : surface;

    final hintColor = isDark ? AppPalette.dark350 : AppPalette.grey500;
    final valueColor = isDark ? AppPalette.dark400 : AppPalette.blue900;
    final chevronColor = isDark ? AppPalette.dark350 : AppPalette.grey500;

    final titleStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs24),
      fontWeight: txt.w600,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final pillValueStyleBold = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs18),
      fontWeight: txt.w600,
      color: valueColor,
      height: 1.0,
    );

    final pillValueStyleRegular = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs18),
      fontWeight: txt.w400,
      color: valueColor,
      height: 1.0,
    );

    final pillHintStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs16),
      fontWeight: txt.w500,
      color: hintColor,
      height: 1.0,
    );

    final commentStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs16),
      fontWeight: txt.w400,
      color: valueColor,
      height: 1.0,
    );

    final commentHintStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs16),
      fontWeight: txt.w500,
      color: hintColor,
      height: 1.0,
    );

    final focusBorderColor = AppPalette.blue500;
    final focusBorderW = dp(context, space.s1);

    return BlocListener<AddRecordBloc, AddRecordState>(
      listenWhen: (prev, curr) => prev != curr,
      listener: (context, state) {
        if (state.isSaved) {
          _clearDraft();
          Navigator.pop(context);
          return;
        }
        _scheduleDraftSave(state);
      },
      child: Scaffold(
        backgroundColor: colors.background,
        body: BlocBuilder<AddRecordBloc, AddRecordState>(
          builder: (context, state) {
            final dt = state.selectedDateTime;
            final showKeypad = state.activeField != InputField.none;

            final isRu = Localizations.localeOf(context).languageCode == 'ru';
            final validationHint = _validationHint(state, isRu);

            if (_noteController.text != state.note) {
              _noteController.value = TextEditingValue(
                text: state.note,
                selection: TextSelection.collapsed(offset: state.note.length),
              );
            }

            return Column(
              children: [
                Container(
                  height: headerH,
                  width: double.infinity,
                  color: headerBg,
                  padding: EdgeInsets.only(
                    left: side,
                    right: side,
                    top: topInset + dp(context, space.s20),
                  ),
                  child: Stack(
                    children: [
                      Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          _tr(context, ru: 'Новая запись', en: 'New record'),
                          style: titleStyle,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      Align(
                        alignment: Alignment.topRight,
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            _HeaderIconButton(icon: Icons.close, onTap: () => Navigator.of(context).pop()),
                            if (widget.isEditing) ...[
                              SizedBox(width: dp(context, space.s8)),
                              _HeaderIconButton(icon: Icons.delete_outline, onTap: () => _confirmDelete(context)),
                            ],
                          ],
                        ),
                      ),
                    ],
                  ),
                ),

                Expanded(
                  child: SingleChildScrollView(
                    padding: EdgeInsets.only(
                      left: side,
                      right: side,
                      top: gap20,
                      bottom: _bottomInset(context),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // SYS / DIA / Pulse — 3 равных поля в ряд (эталон)
                        Row(
                          children: [
                            Expanded(
                              child: _InputPill(
                                height: pillH,
                                radius: pillR,
                                bg: surface,
                                shadow: shadows.card,
                                text: state.systolic.isEmpty ? 'SYS' : state.systolic,
                                textStyle: state.systolic.isEmpty ? pillHintStyle : pillValueStyleBold,
                                isFocused: state.activeField == InputField.systolic,
                                focusBorderColor: focusBorderColor,
                                focusBorderWidth: focusBorderW,
                                onTap: () {
                                  _haptic();
                                  FocusScope.of(context).unfocus();
                                  context.read<AddRecordBloc>().add(const FieldChanged(InputField.systolic));
                                },
                              ),
                            ),
                            SizedBox(width: gap16),
                            Expanded(
                              child: _InputPill(
                                height: pillH,
                                radius: pillR,
                                bg: surface,
                                shadow: shadows.card,
                                text: state.diastolic.isEmpty ? 'DIA' : state.diastolic,
                                textStyle: state.diastolic.isEmpty ? pillHintStyle : pillValueStyleBold,
                                isFocused: state.activeField == InputField.diastolic,
                                focusBorderColor: focusBorderColor,
                                focusBorderWidth: focusBorderW,
                                onTap: () {
                                  _haptic();
                                  FocusScope.of(context).unfocus();
                                  context.read<AddRecordBloc>().add(const FieldChanged(InputField.diastolic));
                                },
                              ),
                            ),
                            SizedBox(width: gap16),
                            Expanded(
                              child: _InputPill(
                                height: pillH,
                                radius: pillR,
                                bg: surface,
                                shadow: shadows.card,
                                text: state.pulse.isEmpty ? _tr(context, ru: 'Пульс', en: 'Pulse') : state.pulse,
                                textStyle: state.pulse.isEmpty ? pillHintStyle : pillValueStyleBold,
                                isFocused: state.activeField == InputField.pulse,
                                focusBorderColor: focusBorderColor,
                                focusBorderWidth: focusBorderW,
                                onTap: () {
                                  _haptic();
                                  FocusScope.of(context).unfocus();
                                  context.read<AddRecordBloc>().add(const FieldChanged(InputField.pulse));
                                },
                              ),
                            ),
                          ],
                        ),

                        SizedBox(height: gap20),

                        // Время (как SYS) + Дата (остаток до правого отступа)
                        _threeColGridSpan23(
                          context: context,
                          gap: gap16,
                          col1: _ChevronPill(
                            height: pillH,
                            radius: pillR,
                            bg: surface,
                            text: DateFormat('HH:mm').format(dt),
                            textStyle: pillValueStyleRegular,
                            chevronColor: chevronColor,
                            shadow: shadows.card,
                            onTap: () {
                              _haptic();
                              _pickTime(context, dt);
                            },
                          ),
                          span23: _ChevronPill(
                            height: pillH,
                            radius: pillR,
                            bg: surface,
                            text: DateFormat('dd MMMM yyyy', Localizations.localeOf(context).toString()).format(dt),
                            textStyle: pillValueStyleRegular,
                            chevronColor: chevronColor,
                            shadow: shadows.card,
                            onTap: () {
                              _haptic();
                              _pickDate(context, dt);
                            },
                          ),
                        ),

                        SizedBox(height: gap20),

                        // Комментарий — стандартная клавиатура
                        Container(
                          height: commentH,
                          decoration: BoxDecoration(
                            color: surface,
                            borderRadius: BorderRadius.circular(pillR),
                            boxShadow: [shadows.card],
                          ),
                          padding: EdgeInsets.fromLTRB(
                            dp(context, space.s14),
                            dp(context, space.s12),
                            dp(context, space.s14),
                            dp(context, space.s12),
                          ),
                          child: TextField(
                            controller: _noteController,
                            focusNode: _noteFocusNode,
                            expands: true,
                            minLines: null,
                            maxLines: null,
                            textAlignVertical: TextAlignVertical.top,
                            onChanged: (v) => context.read<AddRecordBloc>().add(NoteChanged(v)),
                            style: commentStyle,
                            decoration: InputDecoration(
                              border: InputBorder.none,
                              isCollapsed: true,
                              hintText: _tr(context, ru: 'Комментарий', en: 'Comment'),
                              hintStyle: commentHintStyle,
                              suffixIcon: IconButton(
                                tooltip: _tr(context, ru: 'Шаблоны', en: 'Templates'),
                                padding: EdgeInsets.zero,
                                constraints: BoxConstraints(
                                  minWidth: dp(context, space.s32),
                                  minHeight: dp(context, space.s32),
                                ),
                                icon: Icon(
                                  Icons.content_paste,
                                  size: dp(context, space.s20),
                                  color: hintColor,
                                ),
                                onPressed: () {
                                  FocusScope.of(context).unfocus();
                                  context.read<AddRecordBloc>().add(const FieldChanged(InputField.none));
                                  _openCommentTemplatesSheet(context, state.note);
                                },
                              ),
                            ),
                          ),
                        ),

                        SizedBox(height: gap16),

                        // Теги — hint теперь тут (в одной строке с "Теги +")
                        _TagsDisclosureRow(
                          hint: validationHint,
                          isExpanded: state.isTagsExpanded,
                          selectedCount: state.tags.length,
                          onTap: () {
                            _haptic();
                            context.read<AddRecordBloc>().add(TagsExpandedToggled());
                          },
                          textStyle: pillValueStyleRegular,
                        ),

                        if (state.isTagsExpanded) ...[
                          SizedBox(height: dp(context, space.s8)),
                          Wrap(
                            spacing: dp(context, space.s8),
                            runSpacing: dp(context, space.s8),
                            alignment: WrapAlignment.end,
                            children: [
                              for (final tag in AddRecordScreen.presetTags)
                                FilterChip(
                                  selected: state.tags.contains(tag.value),
                                  label: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      SvgPicture.asset(
                                        tag.iconAsset,
                                        width: dp(context, space.s16),
                                        height: dp(context, space.s16),
                                      ),
                                      SizedBox(width: dp(context, space.s6)),
                                      Text(tag.label(context), style: pillValueStyleRegular),
                                    ],
                                  ),
                                  onSelected: (_) {
                                    _haptic();
                                    context.read<AddRecordBloc>().add(TagToggled(tag.value));
                                  },
                                  backgroundColor: surface,
                                ),
                            ],
                          ),
                        ],

                        SizedBox(height: gap16),

                        // Сохранить — 2/3, справа
                        _threeColGridSpan23(
                          context: context,
                          gap: gap16,
                          col1: const SizedBox.shrink(),
                          span23: SizedBox(
                            height: pillH,
                            child: ElevatedButton(
                              onPressed: state.isValid
                                  ? () {
                                _haptic();
                                context.read<AddRecordBloc>().add(SaveSubmitted());
                              }
                                  : null,
                              style: ElevatedButton.styleFrom(
                                elevation: 0,
                                backgroundColor: isDark ? AppPalette.dark800 : colors.brandStrong,
                                disabledBackgroundColor: isDark ? AppPalette.dark700 : AppPalette.grey400,
                                foregroundColor: colors.textOnBrand,
                                disabledForegroundColor: hintColor,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(pillR)),
                              ),
                              child: Text(
                                _tr(context, ru: 'Сохранить', en: 'Save'),
                                style: TextStyle(
                                  fontFamily: txt.family,
                                  fontSize: sp(context, txt.fs20),
                                  fontWeight: txt.w700,
                                  height: 1.0,
                                ),
                              ),
                            ),
                          ),
                        ),

                        if (showKeypad) ...[
                          SizedBox(height: gap20),
                          CustomKeypad(
                            enabledKeys: state.enabledKeys,
                            onKeyPressed: (v) {
                              _haptic();
                              context.read<AddRecordBloc>().add(NumberPressed(v));
                            },
                            onDeletePressed: () {
                              _haptic();
                              context.read<AddRecordBloc>().add(BackspacePressed());
                            },
                            horizontalPadding: 0,
                            gap: keypadGap,
                            cellHeight: keypadCellH,
                            radius: dp(context, radii.r10),
                            background: keypadBg,
                            deleteBackground: keypadBg,
                            foreground: valueColor,
                            textStyle: TextStyle(
                              fontFamily: txt.family,
                              fontSize: sp(context, txt.fs20),
                              fontWeight: txt.w400,
                              height: 1.0,
                              color: valueColor,
                            ),
                            deleteIconSize: dp(context, space.s20),
                            deleteIconColor: valueColor,
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _HeaderIconButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;

  const _HeaderIconButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final space = context.appSpace;

    final size = dp(context, space.s24);
    return SizedBox(
      width: size,
      height: size,
      child: IconButton(
        padding: EdgeInsets.zero,
        constraints: const BoxConstraints(),
        icon: Icon(icon, color: colors.textOnBrand, size: size),
        onPressed: () {
          HapticFeedback.selectionClick();
          onTap();
        },
      ),
    );
  }
}

class _InputPill extends StatelessWidget {
  final double height;
  final double radius;
  final Color bg;
  final BoxShadow shadow;
  final String text;
  final TextStyle textStyle;

  final bool isFocused;
  final Color focusBorderColor;
  final double focusBorderWidth;

  final VoidCallback onTap;

  const _InputPill({
    required this.height,
    required this.radius,
    required this.bg,
    required this.shadow,
    required this.text,
    required this.textStyle,
    required this.isFocused,
    required this.focusBorderColor,
    required this.focusBorderWidth,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        height: height,
        child: Container(
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(radius),
            boxShadow: [shadow],
            border: isFocused ? Border.all(color: focusBorderColor, width: focusBorderWidth) : null,
          ),
          alignment: Alignment.center,
          child: Text(text, style: textStyle, maxLines: 1, overflow: TextOverflow.ellipsis),
        ),
      ),
    );
  }
}

class _ChevronPill extends StatelessWidget {
  final double height;
  final double radius;
  final Color bg;
  final String text;
  final TextStyle textStyle;
  final Color chevronColor;
  final BoxShadow shadow;
  final VoidCallback onTap;

  const _ChevronPill({
    required this.height,
    required this.radius,
    required this.bg,
    required this.text,
    required this.textStyle,
    required this.chevronColor,
    required this.shadow,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final space = context.appSpace;

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: SizedBox(
        height: height,
        child: Container(
          decoration: BoxDecoration(
            color: bg,
            borderRadius: BorderRadius.circular(radius),
            boxShadow: [shadow],
          ),
          padding: EdgeInsets.only(
            left: dp(context, space.s12),
            right: dp(context, space.s8),
          ),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  text,
                  style: textStyle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Icon(
                Icons.arrow_drop_down,
                color: chevronColor,
                size: dp(context, space.s20),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TagsDisclosureRow extends StatelessWidget {
  final bool isExpanded;
  final String? hint;
  final int selectedCount;
  final VoidCallback onTap;

  /// Стиль текста — подаём снаружи, чтобы совпадал с чипами тегов.
  final TextStyle textStyle;

  const _TagsDisclosureRow({
    required this.isExpanded,
    this.hint,
    required this.selectedCount,
    required this.onTap,
    required this.textStyle,
  });

  @override
  Widget build(BuildContext context) {
    final space = context.appSpace;
    final colors = context.appColors;

    final base = _tr(context, ru: 'Теги', en: 'Tags');
    final label = selectedCount == 0 ? base : '$base ($selectedCount)';

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: EdgeInsets.symmetric(
          vertical: dp(context, space.s8),
          horizontal: dp(context, space.s12),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.max,
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            // ✅ Подсказка стоит ПЕРЕД "Теги+"
            if (hint != null) ...[
              Expanded(
                child: Text(
                  hint!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.left,
                  style: textStyle.copyWith(
                    fontWeight: context.appText.w500,
                    color: colors.danger,
                  ),
                ),
              ),
              SizedBox(width: dp(context, space.s10)),
            ],

            // "Теги (n)"
            Text(label, style: textStyle),
            SizedBox(width: dp(context, space.s10)),

            // "+" / "–" в самом конце
            Text(isExpanded ? '–' : '+', style: textStyle),
          ],
        ),
      ),
    );
  }
}
