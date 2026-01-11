// ... файл целиком не повторяю? Нет, правило: только полные замены.
// Поэтому — полный файл, с изменением только _Fab.

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
      child: Builder(
        builder: (context) {
          final bg = Theme.of(context).scaffoldBackgroundColor;
          return Scaffold(
            extendBody: true,
            backgroundColor: bg,
            body: IndexedStack(index: _selectedIndex, children: pages),
            bottomNavigationBar: _BottomNavBar(
              activeIndex: _selectedIndex,
              onTap: _onNavTap,
            ),
          );
        },
      ),
    );
  }
}

class _BottomNavBar extends StatelessWidget {
  final int activeIndex;
  final ValueChanged<int> onTap;

  const _BottomNavBar({
    required this.activeIndex,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final s = context.appSpace;

    final inactive = isDark ? AppPalette.dark400 : AppPalette.blue900; // 2E5D85
    final active = isDark ? AppPalette.dark600 : AppPalette.grey500; // A0AEC0

    final barH = dp(context, s.s72 - s.s2 - s.s1); // 69
    final icon = dp(context, s.s30);

    final outer = dp(context, s.s80 + s.s6); // 86
    final inner = dp(context, s.s56 + s.s4); // 60
    final plus = dp(context, s.s48);

    final lift = outer / 2;

    final barBg = isDark ? AppPalette.dark800 : AppPalette.grey050;

    return SafeArea(
      top: false,
      child: SizedBox(
        height: barH + lift,
        child: Stack(
          clipBehavior: Clip.none,
          alignment: Alignment.bottomCenter,
          children: [
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
                        color: activeIndex == 0 ? active : inactive,
                        onTap: () => onTap(0),
                      ),
                    ),
                    Expanded(
                      child: _NavItem(
                        asset: 'assets/Vector.svg',
                        size: icon,
                        color: activeIndex == 1 ? active : inactive,
                        onTap: () => onTap(1),
                      ),
                    ),
                    SizedBox(width: outer),
                    Expanded(
                      child: _NavItem(
                        asset: 'assets/settings.svg',
                        size: icon,
                        color: activeIndex == 2 ? active : inactive,
                        onTap: () => onTap(3),
                      ),
                    ),
                    Expanded(
                      child: _NavItem(
                        asset: 'assets/user-pen.svg',
                        size: icon,
                        color: activeIndex == 3 ? active : inactive,
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
                    outerColor: barBg, // ✅ внешнее кольцо снова видно
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
  final Color outerColor;

  const _Fab({
    required this.outer,
    required this.inner,
    required this.plus,
    required this.outerColor,
  });

  @override
  Widget build(BuildContext context) {
    final c = context.appColors;
    final s = context.appSpace;

    final shadow = BoxShadow(
      color: c.shadow.withValues(alpha: 0.12), //0.08–0.14 — диапазон “деликатной” тени
      blurRadius: dp(context, s.s10), //чем больше blur, тем мягче
      spreadRadius: dp(context, -s.s2), //Spread < 0 — критично, иначе тень выглядит как обводка
      offset: Offset(0, dp(context, s.s4)), //Offset — маленький, иначе “падает” тяжело
    );

    return SizedBox(
      width: outer,
      height: outer,
      child: Stack(
        alignment: Alignment.center,
        children: [
          // ✅ внешнее кольцо снова НЕ прозрачное
          Container(
            width: outer,
            height: outer,
            decoration: BoxDecoration(
              color: outerColor,
              shape: BoxShape.circle,
              boxShadow: [shadow],
            ),
          ),

          Container(
            width: inner,
            height: inner,
            decoration: BoxDecoration(
              color: c.brandStrong,
              shape: BoxShape.circle,
            ),
            child: Center(
              child: SvgPicture.asset(
                'assets/Plus.svg',
                width: plus,
                height: plus,
                colorFilter: ColorFilter.mode(c.textOnBrand, BlendMode.srcIn),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
