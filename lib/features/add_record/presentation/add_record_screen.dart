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
    debugPrint(
      '### AddRecordScreen BUILD from: lib/features/add_record/presentation/add_record_screen.dart',
    );

    return BlocProvider(
      create: (_) {
        final bloc = GetIt.I<AddRecordBloc>();
        if (record != null) {
          bloc.add(EditStarted(record!));
        }
        return bloc;
      },
      child: AddRecordView(isEditing: record != null),
    );
  }
}

class AddRecordView extends StatefulWidget {
  final bool isEditing;

  const AddRecordView({super.key, required this.isEditing});

  @override
  State<AddRecordView> createState() => _AddRecordViewState();
}

class _AddRecordViewState extends State<AddRecordView> {
  final TextEditingController _noteController = TextEditingController();
  final FocusNode _noteFocusNode = FocusNode();

  double _snapFloor(BuildContext c, double v) {
    final dpr = MediaQuery.of(c).devicePixelRatio;
    return (v * dpr).floorToDouble() / dpr;
  }

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

  Future<void> _pickTime(BuildContext context, DateTime current) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(current),
      helpText: AppStrings.pickTime,
    );
    if (picked == null) return;
    if (!context.mounted) return;

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
    if (picked == null) return;
    if (!context.mounted) return;

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
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        return AlertDialog(
          title: const Text(AppStrings.deleteRecordQ),
          content: const Text(AppStrings.cannotUndo),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: const Text(AppStrings.cancel, style: TextStyle(color: AppUI.buttonBlue)),
            ),
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text(AppStrings.delete, style: TextStyle(color: AppUI.accentRed)),
            ),
          ],
        );
      },
    );

    if (ok == true && context.mounted) {
      context.read<AddRecordBloc>().add(DeleteSubmitted());
    }
  }

  Widget _buildHeader({
    required BuildContext context,
    required bool isEditing,
    required VoidCallback onClose,
    required VoidCallback onDelete,
  }) {
    final pad = dp(context, 20);
    final topInset = MediaQuery.paddingOf(context).top;

    // ВАЖНО: 128dp + статус-бар
    final headerHeight = topInset + dp(context, 128);

    return Container(
      height: headerHeight,
      width: double.infinity,
      color: AppUI.headerBlue,
      padding: EdgeInsets.only(
        left: pad,
        right: pad,
        top: dp(context, 8) + topInset,
        bottom: dp(context, 16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              IconButton(
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
                icon: const Icon(Icons.close, color: AppUI.white),
                onPressed: onClose,
              ),
              const Spacer(),
              if (isEditing)
                IconButton(
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  icon: const Icon(Icons.delete_outline, color: AppUI.white),
                  onPressed: onDelete,
                ),
            ],
          ),
          SizedBox(height: dp(context, 18)),
          Text(
            AppStrings.newRecord,
            style: TextStyle(
              color: AppUI.white,
              fontSize: sp(context, 24),
              fontWeight: FontWeight.w700,
              fontFamily: 'Inter',
              height: 1.0,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final pad = dp(context, 20);
    final topInset = MediaQuery.paddingOf(context).top;

    final pillH = AppUI.fieldHeight;
    final radius = AppUI.fieldRadius;

    const labelColor = AppUI.textLight;
    const valueColor = AppUI.buttonBlue;

    final pillLabelStyle = TextStyle(
      color: labelColor,
      fontSize: sp(context, 14),
      fontWeight: FontWeight.w700,
      fontFamily: 'Inter',
      height: 1.0,
    );

    final pillValueStyle = TextStyle(
      color: valueColor,
      fontSize: sp(context, 18),
      fontWeight: FontWeight.w700,
      fontFamily: 'Inter',
      height: 1.0,
    );

    return BlocListener<AddRecordBloc, AddRecordState>(
      listenWhen: (prev, curr) => curr.isSaved,
      listener: (context, state) => Navigator.pop(context),
      child: Scaffold(
        backgroundColor: AppUI.background,
        body: SafeArea(
          top: false,
          bottom: true,
          child: BlocBuilder<AddRecordBloc, AddRecordState>(
            builder: (context, state) {
              final dt = state.selectedDateTime;
              final showKeypad = state.activeField != InputField.none;

              return Center(
                child: SingleChildScrollView(
                  padding: EdgeInsets.only(
                    bottom: MediaQuery.viewInsetsOf(context).bottom +
                        MediaQuery.paddingOf(context).bottom,
                    top: topInset,
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildHeader(
                        context: context,
                        isEditing: widget.isEditing,
                        onClose: () => Navigator.of(context).pop(),
                        onDelete: () => _confirmDelete(context),
                      ),

                      SizedBox(height: pad),

                      Padding(
                        padding: EdgeInsets.symmetric(horizontal: pad),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            LayoutBuilder(
                              builder: (ctx, cons) {
                                final maxW = cons.maxWidth;
                                final gap = _snapFloor(ctx, pad);
                                final colW = _snapFloor(ctx, (maxW - 2 * gap) / 3);

                                return Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        _ValuePill(
                                          width: colW,
                                          height: pillH,
                                          radius: radius,
                                          label: AppStrings.systolicShort,
                                          value: state.systolic,
                                          isActive: state.activeField == InputField.systolic,
                                          isInvalid: state.systolic.isNotEmpty && !state.systolicValid,
                                          labelStyle: pillLabelStyle,
                                          valueStyle: pillValueStyle,
                                          onTap: () => context
                                              .read<AddRecordBloc>()
                                              .add(const FieldChanged(InputField.systolic)),
                                        ),
                                        SizedBox(width: gap),
                                        _ValuePill(
                                          width: colW,
                                          height: pillH,
                                          radius: radius,
                                          label: AppStrings.diastolicShort,
                                          value: state.diastolic,
                                          isActive: state.activeField == InputField.diastolic,
                                          isInvalid: state.diastolic.isNotEmpty && !state.diastolicValid,
                                          labelStyle: pillLabelStyle,
                                          valueStyle: pillValueStyle,
                                          onTap: () => context
                                              .read<AddRecordBloc>()
                                              .add(const FieldChanged(InputField.diastolic)),
                                        ),
                                        SizedBox(width: gap),
                                        _ValuePill(
                                          width: colW,
                                          height: pillH,
                                          radius: radius,
                                          label: AppStrings.pulse,
                                          value: state.pulse,
                                          isActive: state.activeField == InputField.pulse,
                                          isInvalid: state.pulse.isNotEmpty && !state.pulseValid,
                                          labelStyle: pillLabelStyle,
                                          valueStyle: pillValueStyle,
                                          onTap: () => context
                                              .read<AddRecordBloc>()
                                              .add(const FieldChanged(InputField.pulse)),
                                        ),
                                      ],
                                    ),
                                    SizedBox(height: dp(context, 6)),
                                    Builder(
                                      builder: (_) {
                                        String? err;
                                        if (state.systolic.isNotEmpty && !state.systolicValid) {
                                          err = 'Проверьте систолическое значение';
                                        } else if (state.diastolic.isNotEmpty && !state.diastolicValid) {
                                          err = 'Проверьте диастолическое значение';
                                        } else if (state.pulse.isNotEmpty && !state.pulseValid) {
                                          err = 'Проверьте пульс';
                                        }
                                        return err == null
                                            ? const SizedBox.shrink()
                                            : Text(
                                          err,
                                          style: TextStyle(
                                            color: AppUI.accentRed,
                                            fontSize: sp(context, 14),
                                            fontWeight: FontWeight.w500,
                                            fontFamily: 'Inter',
                                            height: 1.0,
                                          ),
                                        );
                                      },
                                    ),
                                  ],
                                );
                              },
                            ),

                            SizedBox(height: pad),

                            LayoutBuilder(
                              builder: (ctx, cons) {
                                final gap = _snapFloor(ctx, pad);
                                return Row(
                                  children: [
                                    _ChevronPill(
                                      width: AppUI.timeButtonWidth,
                                      height: pillH,
                                      radius: radius,
                                      text: DateFormat('HH:mm').format(dt),
                                      textStyle: pillValueStyle,
                                      chevronColor: labelColor,
                                      onTap: () => _pickTime(context, dt),
                                    ),
                                    SizedBox(width: gap),
                                    _ChevronPill(
                                      width: AppUI.dateButtonWidth,
                                      height: pillH,
                                      radius: radius,
                                      text: DateFormat('dd MMMM yyyy', 'ru').format(dt),
                                      textStyle: pillValueStyle,
                                      chevronColor: labelColor,
                                      onTap: () => _pickDate(context, dt),
                                    ),
                                  ],
                                );
                              },
                            ),

                            SizedBox(height: pad),

                            Container(
                              width: double.infinity,
                              height: dp(context, 72),
                              decoration: BoxDecoration(
                                color: AppUI.white,
                                borderRadius: BorderRadius.circular(radius),
                                boxShadow: const [],
                              ),
                              padding: EdgeInsets.symmetric(
                                horizontal: dp(context, 14),
                                vertical: dp(context, 12),
                              ),
                              alignment: Alignment.topLeft,
                              child: TextField(
                                controller: _noteController,
                                focusNode: _noteFocusNode,
                                expands: true,
                                minLines: null,
                                maxLines: null,
                                textAlignVertical: TextAlignVertical.top,
                                onChanged: (v) => context.read<AddRecordBloc>().add(NoteChanged(v)),
                                style: TextStyle(
                                  color: valueColor,
                                  fontSize: sp(context, 16),
                                  fontFamily: 'Inter',
                                  height: 1.0,
                                ),
                                decoration: InputDecoration.collapsed(
                                  hintText: AppStrings.commentHint,
                                  hintStyle: TextStyle(
                                    color: labelColor,
                                    fontSize: sp(context, 16),
                                    fontFamily: 'Inter',
                                    fontWeight: FontWeight.w600,
                                    height: 1.0,
                                  ),
                                ),
                              ),
                            ),

                            SizedBox(height: pad),

                            const SizedBox.shrink(),

                            SizedBox(height: pad),

                            LayoutBuilder(
                              builder: (ctx, cons) {
                                final maxW = cons.maxWidth;
                                final gap = _snapFloor(ctx, pad);
                                final timeW = _snapFloor(ctx, (maxW - 2 * gap) / 3);
                                final saveW = _snapFloor(ctx, maxW - (gap + timeW));
                                return Align(
                                  alignment: Alignment.centerRight,
                                  child: SizedBox(
                                    width: saveW,
                                    height: pillH,
                                    child: ElevatedButton(
                                      onPressed: state.isValid
                                          ? () => context.read<AddRecordBloc>().add(SaveSubmitted())
                                          : null,
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: AppUI.buttonBlue,
                                        disabledBackgroundColor: AppUI.dividerColor,
                                        foregroundColor: AppUI.white,
                                        disabledForegroundColor: AppUI.textLight,
                                        elevation: 0,
                                        shape: RoundedRectangleBorder(
                                          borderRadius: BorderRadius.circular(radius),
                                        ),
                                      ),
                                      child: Text(
                                        AppStrings.save,
                                        style: TextStyle(
                                          fontSize: sp(context, 18),
                                          fontWeight: FontWeight.w700,
                                          fontFamily: 'Inter',
                                          height: 1.0,
                                        ),
                                      ),
                                    ),
                                  ),
                                );
                              },
                            ),

                            if (showKeypad) ...[
                              SizedBox(height: pad),

                              // ВАЖНО: клавиатура получает те же метрики, что и пилюли
                              LayoutBuilder(
                                builder: (ctx, cons) {
                                  final gap = _snapFloor(ctx, pad);

                                  return CustomKeypad(
                                    enabledKeys: state.enabledKeys,
                                    onKeyPressed: (v) => context.read<AddRecordBloc>().add(NumberPressed(v)),
                                    onDeletePressed: () => context.read<AddRecordBloc>().add(BackspacePressed()),
                                    horizontalPadding: 0, // мы уже внутри Padding(horizontal: pad)
                                    gap: gap,
                                    cellHeight: pillH,
                                    radius: radius,
                                    background: AppUI.white,
                                    deleteBackground: AppUI.dividerColor,
                                    foreground: valueColor,
                                    textStyle: TextStyle(
                                      fontSize: sp(context, 24),
                                      fontWeight: FontWeight.w800,
                                      fontFamily: 'Inter',
                                      height: 1.0,
                                    ),
                                  );
                                },
                              ),
                            ],

                            SizedBox(height: pad),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }
}

class _ValuePill extends StatelessWidget {
  final double width;
  final double height;
  final double radius;
  final String label;
  final String value;
  final bool isActive;
  final bool isInvalid;
  final TextStyle labelStyle;
  final TextStyle valueStyle;
  final VoidCallback onTap;

  const _ValuePill({
    required this.width,
    required this.height,
    required this.radius,
    required this.label,
    required this.value,
    required this.isActive,
    required this.isInvalid,
    required this.labelStyle,
    required this.valueStyle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      height: height,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque, // Чтобы кликалось по всей площади
        onTap: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: AppUI.white,
            borderRadius: BorderRadius.circular(radius),
            boxShadow: const [AppUI.shadow4x2],
            border: (isInvalid || isActive)
                ? Border.all(
              color: isInvalid ? AppUI.accentRed : AppUI.headerBlue,
              width: dp(context, 2),
            )
                : null,
          ),
          alignment: Alignment.center,
          child: Text(
            value.isEmpty ? label : value,
            style: value.isEmpty ? labelStyle : valueStyle,
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}

class _ChevronPill extends StatelessWidget {
  final double width;
  final double height;
  final double radius;
  final String text;
  final TextStyle textStyle;
  final Color chevronColor;
  final VoidCallback onTap;

  const _ChevronPill({
    required this.width,
    required this.height,
    required this.radius,
    required this.text,
    required this.textStyle,
    required this.chevronColor,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final chevronSize = dp(context, 18);
    return SizedBox(
      width: width,
      height: height,
      child: Material( // Добавила Material для нормального InkWell (эффект нажатия)
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(radius),
          onTap: onTap,
          child: Container(
            decoration: BoxDecoration(
              color: AppUI.white,
              borderRadius: BorderRadius.circular(radius),
              boxShadow: const [AppUI.shadow4x2],
            ),
            padding: EdgeInsets.symmetric(horizontal: dp(context, 14)),
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
                SizedBox(width: dp(context, 8)),
                Icon(Icons.keyboard_arrow_down, size: chevronSize, color: chevronColor),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
