import 'message.dart';

sealed class ChatSocketEvent {
  const ChatSocketEvent();
}

final class ChatSocketConnected extends ChatSocketEvent {
  const ChatSocketConnected();
}

final class ChatSocketMessage extends ChatSocketEvent {
  const ChatSocketMessage(this.message);

  final Message message;
}

final class ChatSocketTyping extends ChatSocketEvent {
  const ChatSocketTyping(this.userId);

  final int userId;
}

final class ChatSocketPresence extends ChatSocketEvent {
  const ChatSocketPresence(this.event, this.userId);

  final String event;
  final int userId;
}

final class ChatSocketFailure extends ChatSocketEvent {
  const ChatSocketFailure(this.message);

  final String message;
}

final class ChatSocketClosed extends ChatSocketEvent {
  const ChatSocketClosed();
}

abstract interface class ChatConnection {
  Stream<ChatSocketEvent> get events;

  void sendMessage(String content);

  void sendTyping();

  Future<void> close();
}

abstract interface class ChatRepository {
  Future<ChatConnection> connect(int roomId);
}
