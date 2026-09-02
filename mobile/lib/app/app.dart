import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../core/network/api_client.dart';
import '../features/auth/data/auth_repository_impl.dart';
import '../features/auth/data/token_storage.dart';
import '../features/auth/domain/auth_repository.dart';
import '../features/auth/presentation/auth_bloc.dart';
import '../features/auth/presentation/auth_event.dart';
import 'router.dart';
import 'theme.dart';

class RelaywaveApp extends StatefulWidget {
  const RelaywaveApp({super.key, this.authRepository});

  final AuthRepository? authRepository;

  @override
  State<RelaywaveApp> createState() => _RelaywaveAppState();
}

class _RelaywaveAppState extends State<RelaywaveApp> {
  late final TokenStorage _tokenStorage;
  late final AuthRepository _authRepository;
  late final AuthBloc _authBloc;
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _tokenStorage = SecureTokenStorage();
    _authRepository = widget.authRepository ??
        AuthRepositoryImpl(
          dio: ApiClient(tokenStorage: _tokenStorage).dio,
          tokenStorage: _tokenStorage,
        );
    _authBloc = AuthBloc(_authRepository)..add(const AuthCheckRequested());
    _router = buildRouter(_authBloc);
  }

  @override
  void dispose() {
    _authBloc.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepositoryProvider<AuthRepository>.value(
      value: _authRepository,
      child: BlocProvider<AuthBloc>.value(
        value: _authBloc,
        child: MaterialApp.router(
          title: 'Relaywave',
          theme: AppTheme.light,
          darkTheme: AppTheme.dark,
          themeMode: ThemeMode.system,
          routerConfig: _router,
        ),
      ),
    );
  }
}
