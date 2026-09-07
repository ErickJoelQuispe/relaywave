import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../core/database/app_database.dart';
import '../core/network/api_client.dart';
import '../features/auth/data/auth_repository_impl.dart';
import '../features/auth/data/token_storage.dart';
import '../features/auth/domain/auth_repository.dart';
import '../features/auth/presentation/auth_bloc.dart';
import '../features/auth/presentation/auth_event.dart';
import '../features/chat/data/message_cache.dart';
import '../features/chat/data/ws_chat_repository_impl.dart';
import '../features/chat/domain/chat_repository.dart';
import '../features/friends/data/friends_repository_impl.dart';
import '../features/friends/domain/friends_repository.dart';
import '../features/friends/presentation/friends_bloc.dart';
import '../features/rooms/data/room_cache.dart';
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
    this.friendsRepository,
    this.messageCache,
    this.roomCache,
  });

  final AuthRepository? authRepository;
  final RoomRepository? roomRepository;
  final ChatRepository? chatRepository;
  final FriendsRepository? friendsRepository;
  final MessageCache? messageCache;
  final RoomCache? roomCache;

  @override
  State<RelaywaveApp> createState() => _RelaywaveAppState();
}

class _RelaywaveAppState extends State<RelaywaveApp> {
  late final TokenStorage _tokenStorage;
  late final ApiClient _apiClient;
  late final AuthRepository _authRepository;
  late final RoomRepository _roomRepository;
  late final ChatRepository _chatRepository;
  late final FriendsRepository _friendsRepository;
  late final AppDatabase _database;
  late final MessageCache _messageCache;
  late final RoomCache _roomCache;
  late final AuthBloc _authBloc;
  late final RoomBloc _roomBloc;
  late final FriendsBloc _friendsBloc;
  late final GoRouter _router;

  @override
  void initState() {
    super.initState();
    _tokenStorage = SecureTokenStorage();
    _apiClient = ApiClient(tokenStorage: _tokenStorage);
    _database = AppDatabase();
    _messageCache = widget.messageCache ?? DriftMessageCache(_database);
    _roomCache = widget.roomCache ?? DriftRoomCache(_database);
    _authRepository = widget.authRepository ??
        AuthRepositoryImpl(
          dio: _apiClient.dio,
          tokenStorage: _tokenStorage,
          roomCache: _roomCache,
          messageCache: _messageCache,
        );
    _roomRepository =
        widget.roomRepository ?? RoomRepositoryImpl(dio: _apiClient.dio);
    _chatRepository = widget.chatRepository ??
        ChatRepositoryImpl(dio: _apiClient.dio, tokenStorage: _tokenStorage);
    _friendsRepository =
        widget.friendsRepository ??
        FriendsRepositoryImpl(dio: _apiClient.dio);
    _authBloc = AuthBloc(_authRepository)..add(const AuthCheckRequested());
    _roomBloc = RoomBloc(_roomRepository, cache: _roomCache);
    _friendsBloc = FriendsBloc(_friendsRepository);
    _router = buildRouter(_authBloc);
  }

  @override
  void dispose() {
    _friendsBloc.close();
    _roomBloc.close();
    _authBloc.close();
    unawaited(_database.close());
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
          child: RepositoryProvider<FriendsRepository>.value(
            value: _friendsRepository,
            child: RepositoryProvider<MessageCache>.value(
              value: _messageCache,
              child: RepositoryProvider<RoomCache>.value(
                value: _roomCache,
                child: BlocProvider<AuthBloc>.value(
                  value: _authBloc,
                  child: BlocProvider<RoomBloc>.value(
                    value: _roomBloc,
                    child: BlocProvider<FriendsBloc>.value(
                      value: _friendsBloc,
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
            ),
          ),
        ),
      ),
    );
  }
}
