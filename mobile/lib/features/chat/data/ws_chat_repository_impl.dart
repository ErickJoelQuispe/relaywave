import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../../../core/config/app_config.dart';
import '../../../core/network/api_exception.dart';
import '../../auth/data/token_storage.dart';
import '../domain/chat_repository.dart';
import '../domain/message.dart';

final class ChatRepositoryImpl implements ChatRepository {
  ChatRepositoryImpl({required TokenStorage tokenStorage})
      : _tokenStorage = tokenStorage; // ignore: prefer_initializing_formals

  final TokenStorage _tokenStorage;

  @override
  Future<ChatConnection> connect(int roomId) async {
    final token = await _tokenStorage.readAccessToken();
    if (token == null) {
      throw ApiException('Your session has expired. Please log in again.');
    }
    final uri = Uri.parse('${AppConfig.wsBaseUrl}/ws/rooms/$roomId');
    final channel = WebSocketChannel.connect(uri);
    return _WsChatConnection(channel, token);
  }
}

final class _WsChatConnection implements ChatConnection {
  _WsChatConnection(this._channel, this._token) {
    _wireEvents();
    _sendAuth();
  }

  final WebSocketChannel _channel;
  final String _token;

  final StreamController<ChatSocketEvent> _controller =
      StreamController<ChatSocketEvent>.broadcast();

  bool _connected = false;

  @override
  Stream<ChatSocketEvent> get events => _controller.stream;

  void _sendAuth() {
    _channel.sink.add(jsonEncode({'type': 'auth', 'token': _token}));
  }

  void _wireEvents() {
    _channel.stream.listen(
      _onFrame,
      onError: (Object error) {
        if (_controller.isClosed) return;
        _controller.add(const ChatSocketFailure('Connection error.'));
      },
      onDone: () {
        if (_controller.isClosed) return;
        _controller.add(const ChatSocketClosed());
      },
    );
  }

  void _onFrame(dynamic frame) {
    if (_controller.isClosed) return;
    try {
      final json = jsonDecode(frame as String) as Map<String, dynamic>;
      final type = json['type'];
      if (type is! String) return;

      if (!_connected) {
        _connected = true;
        _controller.add(const ChatSocketConnected());
      }

      switch (type) {
        case 'message':
          _controller.add(ChatSocketMessage(Message.fromJson(json)));
        case 'typing':
          _controller.add(ChatSocketTyping(json['user_id'] as int));
        case 'presence':
          _controller.add(
            ChatSocketPresence(
              json['event'] as String,
              json['user_id'] as int,
            ),
          );
      }
    } catch (_) {
      // Malformed or unexpected frames are ignored by design.
    }
  }

  @override
  void sendMessage(String content) {
    _channel.sink.add(jsonEncode({'type': 'message', 'content': content}));
  }

  @override
  void sendTyping() {
    _channel.sink.add(jsonEncode({'type': 'typing'}));
  }

  @override
  Future<void> close() async {
    await _channel.sink.close();
    await _controller.close();
  }
}
