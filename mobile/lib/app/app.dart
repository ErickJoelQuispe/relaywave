import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../core/network/api_client.dart';
import '../features/auth/data/auth_repository_impl.dart';
import '../features/auth/data/token_storage.dart';
import '../features/auth/domain/auth_repository.dart';
import '../features/auth/presentation/auth_bloc.dart';
import '../features/auth/presentation/auth_event.dart';
import '../features/chat/data/ws_chat_repository_impl.dart';
import '../features/chat/domain/chat_repository.dart';
import '../features/rooms/data/room_repository_impl.dart';
import '../features/rooms/domain/room_repository.dart';
import '../features/rooms/presentation/rooms_bloc.dart';
import 'router.dart';
import 'theme.dart';

class RelaywaveApp extends StatefulWidget {
  const RelaywaveApp({
    super.key,
    this.authRepository,
    this.roomRepository,
    this.chatRepository,
  });

  final AuthRepository? authRepository;
  final RoomRepository? roomRepository;
  final ChatRepository? chatRepository;

  @override
  State<RelaywaveApp> createState() => _RelaywaveAppState();
}

class _RelaywaveAppState extends State<RelaywaveApp> {
  late final TokenStorage _tokenStorage;
  late final ApiClient _apiClient;
  late final AuthRepository _authRepository;
  late final RoomRepository _roomRepository;
  late final ChatRepository _chatRepository;
  late final AuthBloc _authBloc;
  late final RoomBloc _roomBloc;
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _tokenStorage = SecureTokenStorage();
    _apiClient = ApiClient(tokenStorage: _tokenStorage);
    _authRepository = widget.authRepository ??
        AuthRepositoryImpl(
          dio: _apiClient.dio,
          tokenStorage: _tokenStorage,
        );
    _roomRepository =
        widget.roomRepository ?? RoomRepositoryImpl(dio: _apiClient.dio);
    _chatRepository = widget.chatRepository ??
        ChatRepositoryImpl(tokenStorage: _tokenStorage);
    _authBloc = AuthBloc(_authRepository)..add(const AuthCheckRequested());
    _roomBloc = RoomBloc(_roomRepository);
    _router = buildRouter(_authBloc);
  }

  @override
  void dispose() {
    _roomBloc.close();
    _authBloc.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return RepositoryProvider<AuthRepository>.value(
      value: _authRepository,
      child: RepositoryProvider<RoomRepository>.value(
        value: _roomRepository,
        child: RepositoryProvider<ChatRepository>.value(
          value: _chatRepository,
          child: BlocProvider<AuthBloc>.value(
            value: _authBloc,
            child: BlocProvider<RoomBloc>.value(
              value: _roomBloc,
              child: MaterialApp.router(
                title: 'Relaywave',
                theme: AppTheme.light,
                darkTheme: AppTheme.dark,
                themeMode: ThemeMode.system,
                routerConfig: _router,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
