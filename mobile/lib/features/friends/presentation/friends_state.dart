import 'package:equatable/equatable.dart';

import '../domain/friend.dart';

sealed class FriendsState extends Equatable {
  const FriendsState();

  @override
  List<Object?> get props => const [];
}

final class FriendsInitial extends FriendsState {
  const FriendsInitial();

  @override
  List<Object?> get props => const [];
}

final class FriendsLoadInProgress extends FriendsState {
  const FriendsLoadInProgress();

  @override
  List<Object?> get props => const [];
}

final class FriendsLoaded extends FriendsState {
  const FriendsLoaded({
    required this.friends,
    required this.incoming,
    required this.outgoing,
    required this.blocked,
    this.submitting = false,
    this.error,
  });

  final List<Friend> friends;
  final List<FriendRequest> incoming;
  final List<FriendRequest> outgoing;
  final List<Friend> blocked;
  final bool submitting;
  final String? error;

  FriendsLoaded copyWith({
    List<Friend>? friends,
    List<FriendRequest>? incoming,
    List<FriendRequest>? outgoing,
    List<Friend>? blocked,
    bool? submitting,
    String? error,
  }) {
    return FriendsLoaded(
      friends: friends ?? this.friends,
      incoming: incoming ?? this.incoming,
      outgoing: outgoing ?? this.outgoing,
      blocked: blocked ?? this.blocked,
      submitting: submitting ?? this.submitting,
      error: error ?? this.error,
    );
  }

  @override
  List<Object?> get props => [
        friends,
        incoming,
        outgoing,
        blocked,
        submitting,
        error,
      ];
}

final class FriendsLoadFailure extends FriendsState {
  const FriendsLoadFailure(this.message);

  final String message;

  @override
  List<Object?> get props => [message];
}
