import 'package:equatable/equatable.dart';

import '../domain/message.dart';

sealed class ChatState extends Equatable {
  const ChatState();
}

final class ChatConnecting extends ChatState {
  const ChatConnecting();

  @override
  List<Object?> get props => const [];
}

final class ChatActive extends ChatState {
  const ChatActive({
    required this.messages,
    required this.typingUserIds,
    required this.onlineUserIds,
    required this.isConnected,
  });

  final List<Message> messages;
  final Set<int> typingUserIds;
  final Set<int> onlineUserIds;
  final bool isConnected;

  ChatActive copyWith({
    List<Message>? messages,
    Set<int>? typingUserIds,
    Set<int>? onlineUserIds,
    bool? isConnected,
  }) {
    return ChatActive(
      messages: messages ?? this.messages,
      typingUserIds: typingUserIds ?? this.typingUserIds,
      onlineUserIds: onlineUserIds ?? this.onlineUserIds,
      isConnected: isConnected ?? this.isConnected,
    );
  }

  @override
  List<Object?> get props => [
        messages,
        typingUserIds,
        onlineUserIds,
        isConnected,
      ];
}

final class ChatFailed extends ChatState {
  const ChatFailed(this.message);

  final String message;

  @override
  List<Object?> get props => [message];
}
