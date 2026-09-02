import 'package:go_router/go_router.dart';

import '../features/home/presentation/home_screen.dart';

final GoRouter router = GoRouter(
  initialLocation: '/',
  // Auth gating lands in Slice S1.
  redirect: (context, state) => null,
  routes: [
    GoRoute(
      path: '/',
      builder: (context, state) => const HomeScreen(),
    ),
  ],
);
