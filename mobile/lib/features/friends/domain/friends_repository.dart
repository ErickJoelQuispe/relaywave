import '../../rooms/domain/room.dart';
import 'friend.dart';

abstract interface class FriendsRepository {
  /// Submit a friend request by username (uniform "queued" 202, or the
  /// server's 409/422/429 surfaced through ApiException).
  Future<void> sendRequest(String username);

  /// Pending requests in one direction: 'incoming' or 'outgoing'.
  Future<List<FriendRequest>> listRequests({required String direction});

  /// Accept an incoming request; returns the pair's DM room.
  Future<Room> acceptRequest(int userId);

  /// Decline an incoming request.
  Future<void> declineRequest(int userId);

  /// Current friendships (each carries the pair's DM room id).
  Future<List<Friend>> listFriends();

  /// Sever a friendship.
  Future<void> removeFriend(int userId);

  /// Block a user with whom the caller has a relationship.
  Future<void> block(int userId);

  /// Users the caller has blocked (no room ids).
  Future<List<Friend>> listBlocked();

  /// Unblock a user.
  Future<void> unblock(int userId);
}
