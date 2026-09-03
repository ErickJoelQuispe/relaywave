import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';

import '../data/message_cache.dart';
import '../domain/chat_repository.dart';
import '../domain/message.dart';
import 'chat_event.dart';
import 'chat_state.dart';

final class ChatBloc extends Bloc<ChatEvent, ChatState> {
  ChatBloc({
    required ChatRepository repository,
    required MessageCache cache,
    required int roomId,
  })  : _repository = repository, // ignore: prefer_initializing_formals
        _cache = cache, // ignore: prefer_initializing_formals
        _roomId = roomId, // ignore: prefer_initializing_formals
        super(const ChatConnecting()) {
    on<ChatConnectRequested>(_onConnect);
    on<ChatReconnectRequested>(_onReconnect);
    on<ChatMessageSendRequested>(_onMessageSend);
    on<ChatTypingSendRequested>(_onTypingSend);
    on<ChatDisconnectRequested>(_onDisconnect);
  }

  final ChatRepository _repository;
  final MessageCache _cache;
  final int _roomId;

  ChatConnection? _connection;
  final Map<int, Timer> _typingTimers = {};

  int? _lastMessageId;
  Timer? _reconnectTimer;
  int _reconnectAttempt = 0;

  Future<void> _onConnect(
    ChatConnectRequested event,
    Emitter<ChatState> emit,
  ) async {
    await _connect(emit);
  }

  Future<void> _onReconnect(
    ChatReconnectRequested event,
    Emitter<ChatState> emit,
  ) async {
    _reconnectTimer?.cancel();
    await _connect(emit);
  }

  Future<void> _connect(Emitter<ChatState> emit) async {
    await _connection?.close();
    _connection = null;

    List<Message> cached = const [];
    try {
      cached = await _cache.getRecentMessages(_roomId);
      final lastId = await _cache.getLastMessageId(_roomId);
      if (lastId != null && (_lastMessageId == null || lastId > _lastMessageId!)) {
        _lastMessageId = lastId;
      }
    } catch (_) {
      // Best-effort cache read; a miss or failure never blocks connecting.
    }
    // Only seed from cache on the FIRST connect (state is ChatConnecting).
    // On reconnect the in-memory list is already populated via write-through,
    // so re-emitting cached here could drop a just-arrived message.
    if (cached.isNotEmpty && state is! ChatActive && !isClosed && !emit.isDone) {
      emit(
        ChatActive(
          messages: cached,
          typingUserIds: const {},
          onlineUserIds: const {},
          isConnected: true,
        ),
      );
    }

    try {
      final connection = await _repository.connect(_roomId);
      if (isClosed) return;
      _connection = connection;
      unawaited(_backfill(emit));
      await emit.onEach<ChatSocketEvent>(
        connection.events,
        onData: (event) => _onSocketEvent(event, emit),
        onError: (Object error, StackTrace stackTrace) =>
            _onSocketEvent(ChatSocketFailure(error.toString()), emit),
      );
    } catch (_) {
      if (isClosed) return;
      final current = state;
      if (current is ChatActive) {
        // Cached history was already shown; keep it while we retry.
        emit(current.copyWith(isConnected: false));
        _scheduleReconnect();
      } else {
        emit(const ChatFailed('Could not connect to the room.'));
      }
    }
  }

  Future<void> _backfill(Emitter<ChatState> emit) async {
    List<Message> fetched;
    try {
      fetched = await _repository.fetchMessages(_roomId, after: _lastMessageId);
      unawaited(_cache.saveAll(fetched));
    } catch (_) {
      return; // non-fatal; retried on next reconnect
    }
    if (isClosed || emit.isDone) return;
    final current = state;
    final currentMessages =
        current is ChatActive ? current.messages : const <Message>[];
    final byId = <int, Message>{for (final m in currentMessages) m.id: m};
    for (final m in fetched) {
      byId[m.id] = m;
    }
    final merged = byId.values.toList()..sort((a, b) => a.id.compareTo(b.id));
    if (merged.isNotEmpty) _lastMessageId = merged.last.id;
    if (current is ChatActive) {
      emit(current.copyWith(messages: merged));
    } else if (current is ChatConnecting || current is ChatFailed) {
      emit(
        ChatActive(
          messages: merged,
          typingUserIds: const {},
          onlineUserIds: const {},
          isConnected: true,
        ),
      );
    }
  }

  void _scheduleReconnect() {
    _reconnectTimer?.cancel();
    final delay = Duration(seconds: _backoffSeconds(_reconnectAttempt));
    _reconnectAttempt++;
    _reconnectTimer = Timer(delay, () {
      if (isClosed) return;
      add(const ChatReconnectRequested());
    });
  }

  int _backoffSeconds(int attempt) {
    final seconds = 1 << attempt; // 1, 2, 4, 8, 16, 32...
    return seconds.clamp(1, 30);
  }

  void _onSocketEvent(ChatSocketEvent event, Emitter<ChatState> emit) {
    switch (event) {
      case ChatSocketConnected():
        _reconnectAttempt = 0;
        _reconnectTimer?.cancel();
        final current = state;
        if (current is ChatConnecting || current is ChatFailed) {
          emit(
            const ChatActive(
              messages: [],
              typingUserIds: {},
              onlineUserIds: {},
              isConnected: true,
            ),
          );
        } else if (current is ChatActive) {
          emit(current.copyWith(isConnected: true));
        }
      case ChatSocketMessage(:final message):
        final current = state;
        if (current is! ChatActive) return;
        if (current.messages.any((m) => m.id == message.id)) return;
        if (_lastMessageId == null || message.id > _lastMessageId!) {
          _lastMessageId = message.id;
        }
        emit(current.copyWith(messages: [...current.messages, message]));
        unawaited(_cache.save(message));
      case ChatSocketTyping(:final userId):
        final current = state;
        if (current is! ChatActive) return;
        emit(
          current.copyWith(typingUserIds: {...current.typingUserIds, userId}),
        );
        _typingTimers[userId]?.cancel();
        _typingTimers[userId] = Timer(const Duration(seconds: 3), () {
          _typingTimers.remove(userId);
          if (isClosed || emit.isDone) return;
          final current = state;
          if (current is! ChatActive) return;
          final typing = {...current.typingUserIds}..remove(userId);
          emit(current.copyWith(typingUserIds: typing));
        });
      case ChatSocketPresence(:final event, :final userId):
        final current = state;
        if (current is! ChatActive) return;
        final online = {...current.onlineUserIds};
        if (event == 'join') {
          online.add(userId);
        } else {
          online.remove(userId);
        }
        emit(current.copyWith(onlineUserIds: online));
      case ChatSocketFailure(:final message):
        final current = state;
        if (current is ChatConnecting) {
          emit(ChatFailed(message));
        } else if (current is ChatActive) {
          emit(current.copyWith(isConnected: false));
          _scheduleReconnect();
        }
      case ChatSocketClosed():
        final current = state;
        if (current is ChatConnecting) {
          emit(const ChatFailed('Could not connect to the room.'));
        } else if (current is ChatActive) {
          emit(current.copyWith(isConnected: false));
          _scheduleReconnect();
        }
    }
  }

  void _onMessageSend(
    ChatMessageSendRequested event,
    Emitter<ChatState> emit,
  ) {
    _connection?.sendMessage(event.content);
  }

  void _onTypingSend(
    ChatTypingSendRequested event,
    Emitter<ChatState> emit,
  ) {
    _connection?.sendTyping();
  }

  Future<void> _onDisconnect(
    ChatDisconnectRequested event,
    Emitter<ChatState> emit,
  ) async {
    await _connection?.close();
    _connection = null;
  }

  @override
  Future<void> close() async {
    _reconnectTimer?.cancel();
    for (final timer in _typingTimers.values) {
      timer.cancel();
    }
    _typingTimers.clear();
    await _connection?.close();
    _connection = null;
    await super.close();
  }
}
