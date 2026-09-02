import 'package:equatable/equatable.dart';

import '../domain/message.dart';

sealed class ChatEvent extends Equatable {
  const ChatEvent();

  @override
  List<Object?> get props => const [];
}

final class ChatConnectRequested extends ChatEvent {
  const ChatConnectRequested();
}

final class ChatMessageReceived extends ChatEvent {
  const ChatMessageReceived(this.message);

  final Message message;

  @override
  List<Object?> get props => [message];
}

final class ChatTypingReceived extends ChatEvent {
  const ChatTypingReceived(this.userId);

  final int userId;

  @override
  List<Object?> get props => [userId];
}

final class ChatPresenceReceived extends ChatEvent {
  const ChatPresenceReceived(this.event, this.userId);

  final String event;
  final int userId;

  @override
  List<Object?> get props => [event, userId];
}

final class ChatConnectionLost extends ChatEvent {
  const ChatConnectionLost();
}

final class ChatMessageSendRequested extends ChatEvent {
  const ChatMessageSendRequested(this.content);

  final String content;

  @override
  List<Object?> get props => [content];
}

final class ChatTypingSendRequested extends ChatEvent {
  const ChatTypingSendRequested();
}

final class ChatReconnectRequested extends ChatEvent {
  const ChatReconnectRequested();
}

final class ChatDisconnectRequested extends ChatEvent {
  const ChatDisconnectRequested();
}
