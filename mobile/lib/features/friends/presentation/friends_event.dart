import 'package:equatable/equatable.dart';

sealed class FriendsEvent extends Equatable {
  const FriendsEvent();

  @override
  List<Object?> get props => const [];
}

final class FriendsLoadRequested extends FriendsEvent {
  const FriendsLoadRequested();
}

final class FriendAddRequested extends FriendsEvent {
  const FriendAddRequested(this.username);

  final String username;

  @override
  List<Object?> get props => [username];
}

final class FriendAcceptRequested extends FriendsEvent {
  const FriendAcceptRequested(this.userId);

  final int userId;

  @override
  List<Object?> get props => [userId];
}

final class FriendDeclineRequested extends FriendsEvent {
  const FriendDeclineRequested(this.userId);

  final int userId;

  @override
  List<Object?> get props => [userId];
}

final class FriendRemoveRequested extends FriendsEvent {
  const FriendRemoveRequested(this.userId);

  final int userId;

  @override
  List<Object?> get props => [userId];
}

final class FriendUnblockRequested extends FriendsEvent {
  const FriendUnblockRequested(this.userId);

  final int userId;

  @override
  List<Object?> get props => [userId];
}
