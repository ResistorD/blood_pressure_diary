import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:get_it/get_it.dart';
import 'package:intl/intl.dart';

import 'package:blood_pressure_diary/features/home/data/blood_pressure_model.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../core/theme/scale.dart';
import '../../../../core/utils/app_strings.dart';
import '../../../core/utils/input_field.dart';
import 'bloc/add_record_bloc.dart';
import 'bloc/add_record_event.dart';
import 'bloc/add_record_state.dart';
import 'widgets/custom_keypad.dart';

class TagPreset {
  final String label;
  final String iconAsset;

  const TagPreset(this.label, this.iconAsset);
}

class AddRecordScreen extends StatelessWidget {
  static const List<TagPreset> presetTags = [
    TagPreset('После кофе', 'assets/icons/tags/coffee.svg'),
    TagPreset('Алкоголь', 'assets/icons/tags/alcohol.svg'),
    TagPreset('После еды', 'assets/icons/tags/hamburger.svg'),
    TagPreset('После прогулки', 'assets/icons/tags/walk.svg'),
    TagPreset('После тренировки', 'assets/icons/tags/training.svg'),
    TagPreset('Стресс', 'assets/icons/tags/stress.svg'),
    TagPreset('Плохой сон', 'assets/icons/tags/sleep.svg'),
    TagPreset('Головная боль', 'assets/icons/tags/headache.svg'),
    TagPreset('Принял лекарство', 'assets/icons/tags/meds.svg'),
    TagPreset('Пропустил приём', 'assets/icons/tags/missed_meds.svg'),
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

  String? _selectedEmoji;

  @override
  void initState() {
    super.initState();
    _noteFocusNode.addListener(() {
      if (_noteFocusNode.hasFocus) {
        context.read<AddRecordBloc>().add(const FieldChanged(InputField.none));
      }
    });
  }

  @override
  void dispose() {
    _noteController.dispose();
    _noteFocusNode.dispose();
    super.dispose();
  }

  void _appendEmojiToNote(String emoji) {
    final controller = _noteController;

    final text = controller.text;
    final selection = controller.selection;

    final start = selection.isValid ? selection.start : text.length;
    final end = selection.isValid ? selection.end : text.length;

    final newText = text.replaceRange(start, end, emoji);
    controller.value = TextEditingValue(
      text: newText,
      selection: TextSelection.collapsed(offset: start + emoji.length),
    );

    context.read<AddRecordBloc>().add(NoteChanged(newText));
  }

  Future<void> _pickTime(BuildContext context, DateTime current) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
      helpText: AppStrings.pickTime,
    );
    if (picked == null || !context.mounted) return;

    final merged = DateTime(
      current.year,
      current.month,
      current.day,
      picked.hour,
      picked.minute,
    );
    context.read<AddRecordBloc>().add(DateTimeSet(merged));
  }

  Future<void> _pickDate(BuildContext context, DateTime current) async {
    final picked = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(current.year - 1),
      lastDate: DateTime(current.year + 1),
      helpText: AppStrings.pickDate,
    );
    if (picked == null || !context.mounted) return;

    final merged = DateTime(
      picked.year,
      picked.month,
      picked.day,
      current.hour,
      current.minute,
    );
    context.read<AddRecordBloc>().add(DateTimeSet(merged));
  }

  Future<void> _confirmDelete(BuildContext context) async {
    final colors = context.appColors;
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text(AppStrings.deleteRecordQ),
        content: const Text(AppStrings.cannotUndo),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(AppStrings.cancel, style: TextStyle(color: colors.brandStrong)),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(AppStrings.delete, style: TextStyle(color: colors.danger)),
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

    final safeBottom = MediaQuery.paddingOf(context).bottom;
    final keyboard = MediaQuery.viewInsetsOf(context).bottom;

    // Bottom bar in AppNavigation: barH (69) + lift (43) ≈ 112, плюс safeBottom.
    final barH = dp(context, space.s72 - space.s2 - space.s1);
    final outer = dp(context, space.s80 + space.s6);
    final lift = outer / 2;

    return dp(context, space.s96) + barH + lift + safeBottom + dp(context, space.s12) + keyboard;
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

    final emojiSize = dp(context, space.s24);

    final gap20 = dp(context, space.s20);
    final gap16 = dp(context, space.s16);
    final gap12 = dp(context, space.s12);
    final gap10 = dp(context, space.s10);

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final surface = isDark ? AppPalette.dark700 : colors.surface;

    final screenH = MediaQuery.sizeOf(context).height;
    final isSmallScreen = screenH < 700;
    final keypadCellH = isSmallScreen ? (pillH - dp(context, space.s6)) : pillH;
    final keypadGap = isSmallScreen ? dp(context, space.s12) : dp(context, space.s16);
    final keypadBg = isDark ? AppPalette.dark800 : surface;

    final hint = isDark ? AppPalette.dark350 : AppPalette.grey500;
    final value = isDark ? AppPalette.dark400 : AppPalette.blue900;
    final chevron = isDark ? AppPalette.dark350 : AppPalette.grey500;

    final titleStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs24),
      fontWeight: txt.w700,
      color: colors.textOnBrand,
      height: 1.0,
    );

    final pillValueStyleBold = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs18),
      fontWeight: txt.w600,
      color: value,
      height: 1.0,
    );

    final pillValueStyleRegular = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs18),
      fontWeight: txt.w400,
      color: value,
      height: 1.0,
    );

    final pillHintStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs16),
      fontWeight: txt.w500,
      color: hint,
      height: 1.0,
    );

    final commentStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs16),
      fontWeight: txt.w400,
      color: value,
      height: 1.0,
    );

    final commentHintStyle = TextStyle(
      fontFamily: txt.family,
      fontSize: sp(context, txt.fs16),
      fontWeight: txt.w500,
      color: hint,
      height: 1.0,
    );

    final focusBorderColor = isDark ? AppPalette.blue500 : AppPalette.blue500;
    final focusBorderW = dp(context, space.s1);

    return BlocListener<AddRecordBloc, AddRecordState>(
      listenWhen: (prev, curr) => curr.isSaved,
      listener: (context, state) => Navigator.pop(context),
      child: Scaffold(
        backgroundColor: colors.background,
        body: BlocBuilder<AddRecordBloc, AddRecordState>(
          builder: (context, state) {
            final dt = state.selectedDateTime;
            final showKeypad = state.activeField != InputField.none;

            if (_noteController.text != state.note) {
              _noteController.value = TextEditingValue(
                text: state.note,
                selection: TextSelection.collapsed(offset: state.note.length),
              );
            }

            return Column(
              children: [
                Container(
                  height: headerH + topInset,
                  width: double.infinity,
                  color: headerBg,
                  padding: EdgeInsets.only(
                    left: side,
                    right: side,
                    top: topInset + gap12,
                    bottom: gap12,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(height: gap10),
                      Row(
                        children: [
                          _HeaderIconButton(icon: Icons.close, onTap: () => Navigator.of(context).pop()),
                          const Spacer(),
                          if (widget.isEditing)
                            _HeaderIconButton(icon: Icons.delete_outline, onTap: () => _confirmDelete(context)),
                        ],
                      ),
                      SizedBox(height: gap12),
                      Text(
                        AppStrings.newRecord,
                        style: titleStyle,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
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
                                text: state.systolic.isEmpty ? AppStrings.systolicShort : state.systolic,
                                textStyle: state.systolic.isEmpty ? pillHintStyle : pillValueStyleBold,
                                isFocused: state.activeField == InputField.systolic,
                                focusBorderColor: focusBorderColor,
                                focusBorderWidth: focusBorderW,
                                onTap: () => context.read<AddRecordBloc>().add(const FieldChanged(InputField.systolic)),
                              ),
                            ),
                            SizedBox(width: gap16),
                            Expanded(
                              child: _InputPill(
                                height: pillH,
                                radius: pillR,
                                bg: surface,
                                shadow: shadows.card,
                                text: state.diastolic.isEmpty ? AppStrings.diastolicShort : state.diastolic,
                                textStyle: state.diastolic.isEmpty ? pillHintStyle : pillValueStyleBold,
                                isFocused: state.activeField == InputField.diastolic,
                                focusBorderColor: focusBorderColor,
                                focusBorderWidth: focusBorderW,
                                onTap: () => context.read<AddRecordBloc>().add(const FieldChanged(InputField.diastolic)),
                              ),
                            ),
                            SizedBox(width: gap16),
                            Expanded(
                              child: _InputPill(
                                height: pillH,
                                radius: pillR,
                                bg: surface,
                                shadow: shadows.card,
                                text: state.pulse.isEmpty ? AppStrings.pulse : state.pulse,
                                textStyle: state.pulse.isEmpty ? pillHintStyle : pillValueStyleBold,
                                isFocused: state.activeField == InputField.pulse,
                                focusBorderColor: focusBorderColor,
                                focusBorderWidth: focusBorderW,
                                onTap: () => context.read<AddRecordBloc>().add(const FieldChanged(InputField.pulse)),
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
                            chevronColor: chevron,
                            shadow: shadows.card,
                            onTap: () => _pickTime(context, dt),
                          ),
                          span23: _ChevronPill(
                            height: pillH,
                            radius: pillR,
                            bg: surface,
                            text: DateFormat('dd MMMM yyyy', 'ru').format(dt),
                            textStyle: pillValueStyleRegular,
                            chevronColor: chevron,
                            shadow: shadows.card,
                            onTap: () => _pickDate(context, dt),
                          ),
                        ),

                        SizedBox(height: gap20),

                        // Комментарий — на всю ширину минус крайние отступы
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
                            decoration: InputDecoration.collapsed(
                              hintText: AppStrings.commentHint,
                              hintStyle: commentHintStyle,
                            ),
                          ),
                        ),

                        SizedBox(height: gap16),

                        // Теги — по той же ширине, выравнивание по правому краю внутри строки
                        _TagsDisclosureRow(
                          isExpanded: state.isTagsExpanded,
                          selectedCount: state.tags.length,
                          onTap: () => context.read<AddRecordBloc>().add(TagsExpandedToggled()),
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
                                  selected: state.tags.contains(tag.label),
                                  label: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      SvgPicture.asset(
                                        tag.iconAsset,
                                        width: dp(context, space.s16),
                                        height: dp(context, space.s16),
                                      ),
                                      SizedBox(width: dp(context, space.s6)),
                                      Text(tag.label, style: pillValueStyleRegular),
                                    ],
                                  ),
                                  onSelected: (_) => context.read<AddRecordBloc>().add(TagToggled(tag.label)),
                                  backgroundColor: surface,
                                ),
                            ],
                          ),
                        ],

                        SizedBox(height: gap16),

                        // Сохранить — ширина как поле Даты (2/3), выровнено вправо той же структурой
                        _threeColGridSpan23(
                          context: context,
                          gap: gap16,
                          col1: const SizedBox.shrink(),
                          span23: SizedBox(
                            height: pillH,
                            child: ElevatedButton(
                              onPressed: state.isValid ? () => context.read<AddRecordBloc>().add(SaveSubmitted()) : null,
                              style: ElevatedButton.styleFrom(
                                elevation: 0,
                                backgroundColor: isDark ? AppPalette.dark800 : colors.brandStrong,
                                disabledBackgroundColor: isDark ? AppPalette.dark700 : AppPalette.grey400,
                                foregroundColor: colors.textOnBrand,
                                disabledForegroundColor: hint,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(pillR)),
                              ),
                              child: Text(
                                AppStrings.save,
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
                            onKeyPressed: (v) => context.read<AddRecordBloc>().add(NumberPressed(v)),
                            onDeletePressed: () => context.read<AddRecordBloc>().add(BackspacePressed()),
                            horizontalPadding: 0,
                            gap: keypadGap,
                            cellHeight: keypadCellH,
                            radius: dp(context, radii.r10),
                            background: keypadBg,
                            deleteBackground: keypadBg,
                            foreground: value,
                            textStyle: TextStyle(
                              fontFamily: txt.family,
                              fontSize: sp(context, txt.fs20),
                              fontWeight: txt.w400,
                              height: 1.0,
                              color: value,
                            ),
                            deleteIconSize: dp(context, space.s20),
                            deleteIconColor: value,
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
        onPressed: onTap,
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
          padding: EdgeInsets.symmetric(horizontal: dp(context, space.s12)),
          child: Row(
            children: [
              Expanded(child: Text(text, style: textStyle, maxLines: 1, overflow: TextOverflow.ellipsis)),
              Icon(Icons.arrow_drop_down, color: chevronColor, size: dp(context, space.s24)),
            ],
          ),
        ),
      ),
    );
  }
}

class _EmojiButton extends StatelessWidget {
  final String emoji;
  final double size;
  final bool isSelected;
  final VoidCallback onTap;

  const _EmojiButton({
    required this.emoji,
    required this.size,
    required this.isSelected,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final radii = context.appRadii;

    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Container(
        width: size,
        height: size,
        decoration: isSelected
            ? BoxDecoration(
          color: colors.shadow.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(dp(context, radii.r10)),
        )
            : null,
        alignment: Alignment.center,
        child: Text(
          emoji,
          style: TextStyle(
            fontSize: size,
            height: 1.0,
          ),
        ),
      ),
    );
  }
}

class _TagsDisclosureRow extends StatelessWidget {
  final bool isExpanded;
  final int selectedCount;
  final VoidCallback onTap;

  /// Стиль текста — подаём снаружи, чтобы совпадал с чипами тегов.
  final TextStyle textStyle;

  const _TagsDisclosureRow({
    required this.isExpanded,
    required this.selectedCount,
    required this.onTap,
    required this.textStyle,
  });

  @override
  Widget build(BuildContext context) {
    final space = context.appSpace;

    final label = selectedCount == 0 ? 'Теги' : 'Теги ($selectedCount)';

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
            Text(label, style: textStyle),
            SizedBox(width: dp(context, space.s10)),
            Text(isExpanded ? '–' : '+', style: textStyle),
          ],
        ),
      ),
    );
  }
}
