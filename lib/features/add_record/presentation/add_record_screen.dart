import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
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

class AddRecordScreen extends StatelessWidget {
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

  @override
  Widget build(BuildContext context) {
    final colors = context.appColors;
    final space = context.appSpace;
    final radii = context.appRadii;
    final shadows = context.appShadow;
    final txt = context.appText;

    final isDark = Theme.of(context).brightness == Brightness.dark;

    final side = dp(context, space.s20);
    final topInset = MediaQuery.paddingOf(context).top;
    final headerH = dp(context, space.s128);

    final pillH = dp(context, space.s48);
    final pillR = dp(context, radii.r10);
    final pillW = dp(context, space.w96);
    final dateW = dp(context, space.w208);

    final commentW = dp(context, space.w320);
    final commentH = dp(context, space.s72);

    final emojiSize = dp(context, space.s24);

    final gap20 = dp(context, space.s20);
    final gap16 = dp(context, space.s16);
    final gap12 = dp(context, space.s12);
    final gap10 = dp(context, space.s10);
    final gap8 = dp(context, space.s8);

    final headerBg = isDark ? AppPalette.dark800 : AppPalette.blue700;
    final surface = isDark ? AppPalette.dark700 : colors.surface;

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
                  height: headerH,
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
                      Text(AppStrings.newRecord, style: titleStyle),
                    ],
                  ),
                ),

                Expanded(
                  child: SingleChildScrollView(
                    padding: EdgeInsets.only(
                      left: side,
                      right: side,
                      top: gap20,
                      bottom: dp(context, space.s96) + MediaQuery.viewInsetsOf(context).bottom,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            _InputPill(
                              width: pillW,
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
                            _InputPill(
                              width: pillW,
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
                            _InputPill(
                              width: pillW,
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
                          ],
                        ),

                        SizedBox(height: gap20),

                        Row(
                          children: [
                            _ChevronPill(
                              width: pillW,
                              height: pillH,
                              radius: pillR,
                              bg: surface,
                              text: DateFormat('HH:mm').format(dt),
                              textStyle: pillValueStyleRegular,
                              chevronColor: chevron,
                              shadow: shadows.card,
                              onTap: () => _pickTime(context, dt),
                            ),
                            SizedBox(width: gap16),
                            _ChevronPill(
                              width: dateW,
                              height: pillH,
                              radius: pillR,
                              bg: surface,
                              text: DateFormat('dd MMMM yyyy', 'ru').format(dt),
                              textStyle: pillValueStyleRegular,
                              chevronColor: chevron,
                              shadow: shadows.card,
                              onTap: () => _pickDate(context, dt),
                            ),
                          ],
                        ),

                        SizedBox(height: gap20),

                        Align(
                          alignment: Alignment.centerRight,
                          child: Container(
                            width: commentW,
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
                        ),

                        SizedBox(height: gap16),

                        Align(
                          alignment: Alignment.centerRight,
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              // ✅ сердце удалено
                              for (final e in const ['💊', '😀', '🙂', '😒', '🤕']) ...[
                                _EmojiButton(
                                  emoji: e,
                                  size: emojiSize,
                                  isSelected: _selectedEmoji == e,
                                  onTap: () {
                                    setState(() => _selectedEmoji = e);
                                    _appendEmojiToNote(e);
                                  },
                                ),
                                SizedBox(width: gap16),
                              ],
                            ],
                          ),
                        ),

                        SizedBox(height: gap16),

                        Align(
                          alignment: Alignment.centerRight,
                          child: SizedBox(
                            width: dateW,
                            height: pillH,
                            child: ElevatedButton(
                              onPressed: state.isValid ? () => context.read<AddRecordBloc>().add(SaveSubmitted()) : null,
                              style: ElevatedButton.styleFrom(
                                elevation: 0,
                                backgroundColor: colors.brandStrong,
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
                            gap: dp(context, space.s16),
                            cellHeight: pillH,
                            radius: dp(context, radii.r10),
                            background: surface,
                            // ✅ delete-клавиша выглядит как клавиша (тот же фон)
                            deleteBackground: surface,
                            foreground: value,
                            textStyle: TextStyle(
                              fontFamily: txt.family,
                              fontSize: sp(context, txt.fs20),
                              fontWeight: txt.w400,
                              height: 1.0,
                              color: value,
                            ),
                            // ✅ уменьшили примерно на четверть (вместо 26 ставим 20)
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
  final double width;
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
    required this.width,
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
      child: Container(
        width: width,
        height: height,
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.circular(radius),
          boxShadow: [shadow],
          border: isFocused ? Border.all(color: focusBorderColor, width: focusBorderWidth) : null,
        ),
        alignment: Alignment.center,
        child: Text(text, style: textStyle, maxLines: 1, overflow: TextOverflow.ellipsis),
      ),
    );
  }
}

class _ChevronPill extends StatelessWidget {
  final double width;
  final double height;
  final double radius;
  final Color bg;
  final String text;
  final TextStyle textStyle;
  final Color chevronColor;
  final BoxShadow shadow;
  final VoidCallback onTap;

  const _ChevronPill({
    required this.width,
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
      child: Container(
        width: width,
        height: height,
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
