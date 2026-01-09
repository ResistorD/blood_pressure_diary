import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:get_it/get_it.dart';

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
  // 0 Home, 1 Stats, 2 Settings, 3 Profile
  int _selectedIndex = 0;

  void _openAddRecord() {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => const AddRecordScreen()),
    );
  }

  void _onNavTap(int navIndex) {
    // navIndex: 0 Home, 1 Stats, 2 FAB, 3 Settings, 4 Profile
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
        backgroundColor: const Color(0xFFF0F4F8),
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
    const inactive = Color(0xFFBFD4E7);
    const active = Color(0xFF2E5D85);

    final barH = dp(context, 69);
    final icon = dp(context, 30);

    final outer = dp(context, 86);
    final inner = dp(context, 60);
    final plus = dp(context, 48);

    final lift = outer / 2;

    return SafeArea(
      top: false,
      child: SizedBox(
        height: barH + lift, // <- расширили только хиттест, НЕ бар
        child: Stack(
          clipBehavior: Clip.none,
          alignment: Alignment.bottomCenter,
          children: [
            // ФОН БАРА — строго внизу, высота не меняется визуально
            Positioned(
              left: 0,
              right: 0,
              bottom: 0,
              height: barH,
              child: Container(
                color: const Color(0xFFF9F8FA),
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

            // FAB — визуально как было: наполовину выше бара
            Positioned(
              // верх круга будет над баром, но ХИТТЕСТ теперь внутри SizedBox(barH+lift)
              bottom: barH - lift,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => onTap(2),
                child: SizedBox(
                  width: outer,
                  height: outer,
                  child: _Fab(outer: outer, inner: inner, plus: plus),
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
    return Center(
      child: GestureDetector(
        onTap: onTap,
        behavior: HitTestBehavior.opaque,
        child: SizedBox(
          width: dp(context, 56),
          height: dp(context, 56),
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

  const _Fab({required this.outer, required this.inner, required this.plus});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: outer,
      height: outer,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Container(
            width: outer,
            height: outer,
            decoration: BoxDecoration(
              color: const Color(0xFFF9F8FA),
              shape: BoxShape.circle,
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.08),
                  blurRadius: dp(context, 12),
                  offset: const Offset(0, 4),
                ),
              ],
            ),
          ),
          Container(
            width: inner,
            height: inner,
            decoration: const BoxDecoration(
              color: Color(0xFF2E5D85),
              shape: BoxShape.circle,
            ),
            child: Center(
              child: SvgPicture.asset(
                'assets/Plus.svg',
                width: plus,
                height: plus,
                colorFilter: const ColorFilter.mode(Colors.white, BlendMode.srcIn),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
