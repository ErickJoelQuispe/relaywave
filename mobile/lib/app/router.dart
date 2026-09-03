import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../features/auth/presentation/auth_bloc.dart';
import '../features/auth/presentation/auth_state.dart';
import '../features/auth/presentation/login_screen.dart';
import '../features/auth/presentation/register_screen.dart';
import '../features/auth/presentation/splash_screen.dart';
import '../features/chat/presentation/chat_screen.dart';
import '../features/rooms/presentation/rooms_pane.dart';
import 'responsive_shell.dart';

class GoRouterRefreshStream extends ChangeNotifier {
  GoRouterRefreshStream(Stream<dynamic> stream) {
    notifyListeners();
    _subscription = stream.asBroadcastStream().listen((_) => notifyListeners());
  }

  late final StreamSubscription<dynamic> _subscription;

  @override
  void dispose() {
    _subscription.cancel();
    super.dispose();
  }
}

GoRouter buildRouter(AuthBloc authBloc) {
  return GoRouter(
    initialLocation: '/',
    refreshListenable: GoRouterRefreshStream(authBloc.stream),
    redirect: (context, state) {
      final location = state.matchedLocation;
      return switch (authBloc.state) {
        AuthUnknown() => location == '/splash' ? null : '/splash',
        AuthLoading() => null,
        AuthAuthenticated() => switch (location) {
            '/login' || '/register' || '/splash' => '/',
            _ => null,
          },
        AuthUnauthenticated() => switch (location) {
            '/login' || '/register' => null,
            _ => '/login',
          },
      };
    },
    routes: [
      GoRoute(
        path: '/splash',
        builder: (context, state) => const SplashScreen(),
      ),
      GoRoute(
        path: '/login',
        builder: (context, state) => const LoginScreen(),
      ),
      GoRoute(
        path: '/register',
        builder: (context, state) => const RegisterScreen(),
      ),
      ShellRoute(
        builder: (context, state, child) =>
            ResponsiveShell(state: state, child: child),
        routes: [
          GoRoute(
            path: '/',
            builder: (context, state) => const RoomsPane(),
          ),
          GoRoute(
            path: '/rooms/:id',
            builder: (context, state) {
              final roomId = int.parse(state.pathParameters['id']!);
              final roomName = state.uri.queryParameters['name'] ?? 'Room';
              return ChatScreen(roomId: roomId, roomName: roomName);
            },
          ),
        ],
      ),
    ],
  );
}
