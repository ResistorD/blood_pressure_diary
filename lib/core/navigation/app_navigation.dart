import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:get_it/get_it.dart';

import '../theme/app_theme.dart';
import '../theme/scale.dart';

import '../../features/home/presentation/home_screen.dart';
import '../../features/home/presentation/statistics_screen.dart';
import '../../features/settings/presentation/settings_screen.dart';
import '../../features/profile/presentation/profile_screen.dart';
import '../../features/add_record/presentation/add_record_screen.dart';
import '../../features/home/presentation/bloc/home_bloc.dart';
import '../../features/profile/presentation/bloc/profile_cubit.dart';
import '../../features/settings/presentation/bloc/settings_cubit.dart';

class AppNavigation extends StatefulWidget {
  const AppNavigation({super.key});

  @override
  State<AppNavigation> createState() => _AppNavigationState();
}

class _AppNavigationState extends State<AppNavigation> {
  int _selectedIndex = 0;

  void _openAddRecord() {
    Navigator.push(context, MaterialPageRoute(builder: (_) => const AddRecordScreen()));
  }

  void _onNavTap(int navIndex) {
    if (navIndex == 2) {
      _openAddRecord();
      return;
    }
    final pageIndex = (navIndex < 2) ? navIndex : (navIndex - 1);
    setState(() => _selectedIndex = pageIndex);
  }

  @override
  Widget build(BuildContext context) {
    final pages = <Widget>[
      const HomeScreen(),
      const StatisticsScreen(),
      const SettingsScreen(),
      const ProfileScreen(),
    ];

    return MultiBlocProvider(
      providers: [
        BlocProvider(create: (_) => GetIt.I<HomeBloc>()),
        BlocProvider.value(value: GetIt.I<ProfileCubit>()..loadProfile()),
        BlocProvider.value(value: GetIt.I<SettingsCubit>()),
      ],
      child: Scaffold(
        extendBody: true,
        body: IndexedStack(index: _selectedIndex, children: pages),
        bottomNavigationBar: _BottomNavBar(
          activeIndex: _selectedIndex,
          onTap: _onNavTap,
        ),
      ),
    );
  }
}

class _BottomNavBar extends StatelessWidget {
  final int activeIndex; // 0..3
  final ValueChanged<int> onTap; // 0..4 (2 is center)

  const _BottomNavBar({
    required this.activeIndex,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final s = context.appSpace;

    // ✅ В dark: активная БЛЕДНАЯ, остальные ЯРКИЕ
    final bright = isDark ? AppPalette.dark400 : AppPalette.blue900; // яркая
    final pale = isDark ? AppPalette.dark600 : AppPalette.grey500;  // бледная

    final barH = dp(context, s.s72 - s.s2 - s.s1); // 69
    final icon = dp(context, s.s30);

    final outer = dp(context, s.s80 + s.s6); // 86
    final inner = dp(context, s.s56 + s.s4); // 60
    final plus = dp(context, s.s48);

    final lift = outer / 2;

    // ✅ Фон нижнего меню dark: #3C3C3C
    final barBg = isDark ? AppPalette.dark800 : AppPalette.grey050;

    return SafeArea(
      top: false,
      child: SizedBox(
        height: barH + lift,
        child: Stack(
          clipBehavior: Clip.none,
          alignment: Alignment.bottomCenter,
          children: [
            // Подложка под поднятую кнопку — прозрачная (как ты и говорил)
            Positioned.fill(child: const ColoredBox(color: Colors.transparent)),

            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              height: barH,
              child: Container(
                color: barBg,
                child: Row(
                  children: [
                    Expanded(
                      child: _NavItem(
                        asset: 'assets/house.svg',
                        size: icon,
                        color: activeIndex == 0 ? pale : bright,
                        onTap: () => onTap(0),
                      ),
                    ),
                    Expanded(
                      child: _NavItem(
                        asset: 'assets/Vector.svg',
                        size: icon,
                        color: activeIndex == 1 ? pale : bright,
                        onTap: () => onTap(1),
                      ),
                    ),
                    SizedBox(width: outer),
                    Expanded(
                      child: _NavItem(
                        asset: 'assets/settings.svg',
                        size: icon,
                        color: activeIndex == 2 ? pale : bright,
                        onTap: () => onTap(3),
                      ),
                    ),
                    Expanded(
                      child: _NavItem(
                        asset: 'assets/user-pen.svg',
                        size: icon,
                        color: activeIndex == 3 ? pale : bright,
                        onTap: () => onTap(4),
                      ),
                    ),
                  ],
                ),
              ),
            ),

            Positioned(
              bottom: barH - lift,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => onTap(2),
                child: SizedBox(
                  width: outer,
                  height: outer,
                  child: _Fab(
                    outer: outer,
                    inner: inner,
                    plus: plus,
                    isDark: isDark,
                    barBg: barBg,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final String asset;
  final double size;
  final Color color;
  final VoidCallback onTap;

  const _NavItem({
    required this.asset,
    required this.size,
    required this.color,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final s = context.appSpace;
    final hit = dp(context, s.s56);

    return Center(
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: SizedBox(
          width: hit,
          height: hit,
          child: Center(
            child: SvgPicture.asset(
              asset,
              width: size,
              height: size,
              colorFilter: ColorFilter.mode(color, BlendMode.srcIn),
            ),
          ),
        ),
      ),
    );
  }
}

class _Fab extends StatelessWidget {
  final double outer;
  final double inner;
  final double plus;
  final bool isDark;
  final Color barBg;

  const _Fab({
    required this.outer,
    required this.inner,
    required this.plus,
    required this.isDark,
    required this.barBg,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    final s = context.appSpace;

    final shadow = BoxShadow(
      color: AppPalette.shadow10,
      blurRadius: dp(context, s.s4),
      offset: Offset(0, dp(context, s.s2)),
    );

    final innerBg = isDark ? AppPalette.dark900 : c.brandStrong;
    final plusColor = isDark ? AppPalette.dark400 : c.textOnBrand;

    final outerDecoration = BoxDecoration(
      shape: BoxShape.circle,
      boxShadow: [shadow],
      color: isDark ? null : barBg,
      gradient: isDark
          ? const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          AppPalette.dark800, // #3C3C3C
          AppPalette.dark805, // #3D3D3D
        ],
      )
          : null,
    );

    return SizedBox(
      width: outer,
      height: outer,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: outer,
            height: outer,
            decoration: outerDecoration,
          ),
          Container(
            width: inner,
            height: inner,
            decoration: BoxDecoration(
              color: innerBg,
              shape: BoxShape.circle,
            ),
            child: Center(
              child: SvgPicture.asset(
                'assets/Plus.svg',
                width: plus,
                height: plus,
                colorFilter: ColorFilter.mode(plusColor, BlendMode.srcIn),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
