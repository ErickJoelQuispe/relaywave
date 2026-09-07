import 'package:equatable/equatable.dart';

/// A user with whom the caller has a relationship (F1-R7).
///
/// Usernames are resolved server-side and only ever for users with whom the
/// caller has that exact relationship — this model never holds another
/// account's data beyond the relationship surface.
final class Friend extends Equatable {
  const Friend({
    required this.id,
    required this.username,
    this.roomId,
  });

  final int id;
  final String username;

  /// The pair's DM room id (present on the friends list, absent on the
  /// blocked list, which has no room).
  final int? roomId;

  factory Friend.fromJson(Map<String, dynamic> json) => Friend(
        id: json['user_id'] as int,
        username: json['username'] as String,
        roomId: json['room_id'] as int?,
      );

  @override
  List<Object?> get props => [id, username, roomId];
}

/// A pending friend request, incoming or outgoing (F1-R3).
final class FriendRequest extends Equatable {
  const FriendRequest({
    required this.id,
    required this.username,
    required this.createdAt,
  });

  final int id;
  final String username;
  final DateTime createdAt;

  factory FriendRequest.fromJson(Map<String, dynamic> json) => FriendRequest(
        id: json['user_id'] as int,
        username: json['username'] as String,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  @override
  List<Object?> get props => [id, username, createdAt];
}
