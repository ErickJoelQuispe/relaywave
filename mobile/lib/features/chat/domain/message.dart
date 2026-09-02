import 'package:equatable/equatable.dart';

final class Message extends Equatable {
  const Message({
    required this.id,
    required this.roomId,
    required this.senderId,
    required this.content,
    required this.createdAt,
  });

  final int id;
  final int roomId;
  final int senderId;
  final String content;
  final DateTime createdAt;

  factory Message.fromJson(Map<String, dynamic> json) => Message(
        id: json['id'] as int,
        roomId: json['room_id'] as int,
        senderId: json['sender_id'] as int,
        content: json['content'] as String,
        createdAt: DateTime.parse(json['created_at'] as String).toLocal(),
      );

  @override
  List<Object?> get props => [id];
}
