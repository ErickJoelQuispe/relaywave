import 'dart:async';

import 'package:drift/drift.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:relaywave_mobile/app/app.dart';
import 'package:relaywave_mobile/features/auth/domain/auth_repository.dart';
import 'package:relaywave_mobile/features/auth/domain/user.dart';
import 'package:relaywave_mobile/features/chat/data/message_cache.dart';
import 'package:relaywave_mobile/features/chat/domain/chat_repository.dart';
import 'package:relaywave_mobile/features/chat/domain/message.dart';
import 'package:relaywave_mobile/features/friends/domain/friend.dart';
import 'package:relaywave_mobile/features/friends/domain/friends_repository.dart';
import 'package:relaywave_mobile/features/rooms/data/room_cache.dart';
import 'package:relaywave_mobile/features/rooms/domain/room.dart';
import 'package:relaywave_mobile/features/rooms/domain/room_repository.dart';

class _FakeRoomRepository implements RoomRepository {
  _FakeRoomRepository({
    List<Room> rooms = const <Room>[],
    this.listRoomsGate,
  }) : rooms = List.of(rooms);

  final List<Room> rooms;
  final Completer<List<Room>>? listRoomsGate;

  /// The last input passed to [getRoomByName] (null if never called).
  String? resolvedByName;

  /// The last room id passed to [joinRoom] (null if never called).
  int? joinedRoomId;

  @override
  Future<List<Room>> listRooms() async {
    if (listRoomsGate != null) return listRoomsGate!.future;
    return List.of(rooms);
  }

  @override
  Future<Room> createRoom(String name) {
    throw UnimplementedError();
  }

  @override
  Future<Room> getRoom(int roomId) async {
    return rooms.firstWhere((room) => room.id == roomId);
  }

  @override
  Future<Room> getRoomByName(String name) async {
    resolvedByName = name;
    // Mimic the server's canonical_slug: lowercase + collapse non-slug runs.
    final slug = name
        .toLowerCase()
        .replaceAll(RegExp('[^a-z0-9]+'), '-')
        .replaceAll(RegExp('^-|-\$'), '');
    return rooms.firstWhere((room) => room.name == slug);
  }

  @override
  Future<void> joinRoom(int roomId) async {
    joinedRoomId = roomId;
  }
}

class _FakeAuthRepository implements AuthRepository {
  @override
  Future<User?> restoreSession() async => null;

  @override
  Future<User> login(String email, String password) {
    throw UnimplementedError();
  }

  @override
  Future<User> register(String email, String username, String password) {
    throw UnimplementedError();
  }

  @override
  Future<void> logout() {
    throw UnimplementedError();
  }
}

class _FakeAuthenticatedRepository implements AuthRepository {
  static final User _user = User(
    id: 1,
    email: 'user@example.com',
    username: 'alice',
    createdAt: DateTime.utc(2026, 1, 1),
  );

  @override
  Future<User?> restoreSession() async => _user;

  @override
  Future<User> login(String email, String password) {
    throw UnimplementedError();
  }

  @override
  Future<User> register(String email, String username, String password) {
    throw UnimplementedError();
  }

  @override
  Future<void> logout() {
    throw UnimplementedError();
  }
}

class _FakeChatConnection implements ChatConnection {
  _FakeChatConnection(this._controller);

  final StreamController<ChatSocketEvent> _controller;

  @override
  Stream<ChatSocketEvent> get events => _controller.stream;

  @override
  void sendMessage(String content) {}

  @override
  void sendTyping() {}

  @override
  Future<void> close() async {
    await _controller.close();
  }
}

class _FakeChatRepository implements ChatRepository {
  _FakeChatRepository({this.history = const <Message>[]});

  List<Message> history;
  int connectCount = 0;

  final List<StreamController<ChatSocketEvent>> _controllers = [];

  StreamController<ChatSocketEvent> get _latestController => _controllers.last;

  void add(ChatSocketEvent event) => _latestController.add(event);

  @override
  Future<ChatConnection> connect(int roomId) async {
    connectCount++;
    final controller = StreamController<ChatSocketEvent>.broadcast();
    _controllers.add(controller);
    return _FakeChatConnection(controller);
  }

  @override
  Future<List<Message>> fetchMessages(
    int roomId, {
    int? after,
    int limit = 100,
  }) async {
    return history;
  }
}

class _FakeMessageCache implements MessageCache {
  _FakeMessageCache({
    List<Message> messages = const <Message>[],
    this.lastMessageId,
  }) : messages = List.of(messages);

  final List<Message> messages;
  int? lastMessageId;

  @override
  Future<List<Message>> getRecentMessages(int roomId, {int limit = 100}) async {
    return messages.where((m) => m.roomId == roomId).toList();
  }

  @override
  Future<int?> getLastMessageId(int roomId) async => lastMessageId;

  @override
  Future<void> save(Message message) async {
    messages.removeWhere((m) => m.id == message.id);
    messages.add(message);
  }

  @override
  Future<void> saveAll(Iterable<Message> messages) async {
    for (final message in messages) {
      this.messages.removeWhere((m) => m.id == message.id);
      this.messages.add(message);
    }
  }

  @override
  Future<void> clear() async => messages.clear();
}

class _FakeRoomCache implements RoomCache {
  _FakeRoomCache({List<Room> rooms = const <Room>[]}) : rooms = List.of(rooms);

  final List<Room> rooms;

  @override
  Future<List<Room>> getRooms() async => List.of(rooms);

  @override
  Future<void> saveAll(Iterable<Room> rooms) async {
    this.rooms
      ..clear()
      ..addAll(rooms);
  }

  @override
  Future<void> clear() async => rooms.clear();
}

class _FakeFriendsRepository implements FriendsRepository {
  _FakeFriendsRepository({
    List<Friend> friends = const <Friend>[],
    List<FriendRequest> incoming = const <FriendRequest>[],
    List<FriendRequest> outgoing = const <FriendRequest>[],
    List<Friend> blocked = const <Friend>[],
  }) : friends = List.of(friends),
       incoming = List.of(incoming),
       outgoing = List.of(outgoing),
       blocked = List.of(blocked);

  final List<Friend> friends;
  final List<FriendRequest> incoming;
  final List<FriendRequest> outgoing;
  final List<Friend> blocked;

  final List<String> sentUsernames = [];
  int? acceptedUserId;
  int? declinedUserId;
  int? removedUserId;
  int? unblockedUserId;

  @override
  Future<void> sendRequest(String username) async {
    sentUsernames.add(username);
    outgoing.add(
      FriendRequest(
        id: 900 + outgoing.length,
        username: username,
        createdAt: DateTime.utc(2026, 1, 1),
      ),
    );
  }

  @override
  Future<List<FriendRequest>> listRequests({
    required String direction,
  }) async {
    return direction == 'incoming'
        ? List.of(incoming)
        : List.of(outgoing);
  }

  @override
  Future<Room> acceptRequest(int userId) async {
    acceptedUserId = userId;
    final request = incoming.firstWhere((r) => r.id == userId);
    incoming.remove(request);
    friends.add(
      Friend(id: request.id, username: request.username, roomId: 500),
    );
    return Room(
      id: 500,
      name: 'dm-1-2',
      kind: 'dm',
      peerUsername: request.username,
      createdAt: DateTime.utc(2026, 1, 1),
    );
  }

  @override
  Future<void> declineRequest(int userId) async {
    declinedUserId = userId;
    incoming.removeWhere((r) => r.id == userId);
  }

  @override
  Future<List<Friend>> listFriends() async => List.of(friends);

  @override
  Future<void> removeFriend(int userId) async {
    removedUserId = userId;
    friends.removeWhere((f) => f.id == userId);
  }

  @override
  Future<void> block(int userId) {
    throw UnimplementedError();
  }

  @override
  Future<List<Friend>> listBlocked() async => List.of(blocked);

  @override
  Future<void> unblock(int userId) async {
    unblockedUserId = userId;
    blocked.removeWhere((f) => f.id == userId);
  }
}

void main() {
  // Each test pumps a fresh RelaywaveApp, which constructs a new AppDatabase.
  // These instances never share a QueryExecutor (the real DB is never opened
  // because fakes are injected), so suppress drift's debug-only multi-instance
  // warning.
  driftRuntimeOptions.dontWarnAboutMultipleDatabases = true;

  final sampleRoom = Room(
    id: 1,
    name: 'general',
    createdAt: DateTime.utc(2026, 1, 1),
  );

  testWidgets('shows the login screen when unauthenticated', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthRepository(),
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Log in'), findsOneWidget);
  });

  testWidgets('shows the rooms screen when authenticated', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(),
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Rooms'), findsOneWidget);
  });

  testWidgets('shows a chat message when a room is opened', (
    WidgetTester tester,
  ) async {
    final chatRepository = _FakeChatRepository();
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(rooms: [sampleRoom]),
        chatRepository: chatRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('general'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    chatRepository.add(const ChatSocketConnected());
    await tester.pump();

    chatRepository.add(
      ChatSocketMessage(
        Message(
          id: 1,
          roomId: 1,
          senderId: 2,
          content: 'hello world',
          createdAt: DateTime.utc(2026, 1, 1),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('hello world'), findsOneWidget);
  });

  testWidgets('backfills message history when a room is opened', (
    WidgetTester tester,
  ) async {
    final chatRepository = _FakeChatRepository(
      history: [
        Message(
          id: 1,
          roomId: 1,
          senderId: 2,
          content: 'first message',
          createdAt: DateTime.utc(2026, 1, 1),
        ),
        Message(
          id: 2,
          roomId: 1,
          senderId: 2,
          content: 'second message',
          createdAt: DateTime.utc(2026, 1, 1),
        ),
      ],
    );
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(rooms: [sampleRoom]),
        chatRepository: chatRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('general'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpAndSettle();

    expect(find.text('first message'), findsOneWidget);
    expect(find.text('second message'), findsOneWidget);
  });

  testWidgets('deduplicates a live message that overlaps backfill', (
    WidgetTester tester,
  ) async {
    final message = Message(
      id: 1,
      roomId: 1,
      senderId: 2,
      content: 'hello world',
      createdAt: DateTime.utc(2026, 1, 1),
    );
    final chatRepository = _FakeChatRepository(history: [message]);
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(rooms: [sampleRoom]),
        chatRepository: chatRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('general'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    chatRepository.add(ChatSocketMessage(message));
    await tester.pump();
    await tester.pumpAndSettle();

    expect(find.text('hello world'), findsOneWidget);
  });

  testWidgets('auto-reconnects after the connection closes', (
    WidgetTester tester,
  ) async {
    final chatRepository = _FakeChatRepository();
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(rooms: [sampleRoom]),
        chatRepository: chatRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('general'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));

    expect(chatRepository.connectCount, 1);

    chatRepository.add(const ChatSocketClosed());
    await tester.pump();

    await tester.pump(const Duration(seconds: 1));

    expect(chatRepository.connectCount, 2);
  });

  testWidgets('shows master and detail panes on wide screens', (
    WidgetTester tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(1200, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(),
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('No rooms yet. Create or join one.'), findsOneWidget);
    expect(find.text('Select a room to start chatting'), findsOneWidget);
  });

  testWidgets('renders cached history before any live socket event', (
    WidgetTester tester,
  ) async {
    final cachedMessage = Message(
      id: 42,
      roomId: 1,
      senderId: 2,
      content: 'cached hello',
      createdAt: DateTime.utc(2026, 1, 1),
    );
    final messageCache = _FakeMessageCache(
      messages: [cachedMessage],
      lastMessageId: 42,
    );
    final chatRepository = _FakeChatRepository();
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(rooms: [sampleRoom]),
        chatRepository: chatRepository,
        messageCache: messageCache,
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('general'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    await tester.pumpAndSettle();

    // The cached message renders before any ChatSocketEvent is emitted.
    expect(find.text('cached hello'), findsOneWidget);
    expect(chatRepository.connectCount, 1);
  });

  testWidgets('writes a live message through to the cache', (
    WidgetTester tester,
  ) async {
    final messageCache = _FakeMessageCache();
    final chatRepository = _FakeChatRepository();
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(rooms: [sampleRoom]),
        chatRepository: chatRepository,
        messageCache: messageCache,
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('general'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    chatRepository.add(const ChatSocketConnected());
    await tester.pump();

    final liveMessage = Message(
      id: 7,
      roomId: 1,
      senderId: 2,
      content: 'live write',
      createdAt: DateTime.utc(2026, 1, 1),
    );
    chatRepository.add(ChatSocketMessage(liveMessage));
    await tester.pump();
    await tester.pump();
    await tester.pumpAndSettle();

    expect(messageCache.messages.any((m) => m.id == 7), isTrue);
  });

  testWidgets('renders cached rooms before the network returns', (
    WidgetTester tester,
  ) async {
    final gate = Completer<List<Room>>();
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(listRoomsGate: gate),
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(rooms: [sampleRoom]),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('general'), findsOneWidget);

    gate.complete(const <Room>[]);
    await tester.pump();
  });

  testWidgets('joins a room by typed name through the repository', (
    WidgetTester tester,
  ) async {
    final repository = _FakeRoomRepository(rooms: [sampleRoom]);
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: repository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    // Open the join dialog and type free text (not a numeric id).
    await tester.tap(find.byTooltip('Join a room'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'General');
    await tester.tap(find.text('Join'));
    await tester.pumpAndSettle();

    // The free text resolved through getRoomByName, then reused the id join,
    // and the room list shows the canonical slug tile.
    expect(repository.resolvedByName, 'General');
    expect(repository.joinedRoomId, 1);
    expect(find.text('general'), findsOneWidget);
  });

  testWidgets('chat header titles from server detail and labels the estimate',
      (tester) async {
    final chatRepository = _FakeChatRepository();
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(rooms: [sampleRoom]),
        chatRepository: chatRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('general'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    chatRepository.add(const ChatSocketConnected());
    await tester.pump();
    // A presence delta arrives on the live socket: 1 user online.
    chatRepository.add(const ChatSocketPresence('join', 42));
    await tester.pump();
    await tester.pump();

    // F3-R1: title comes from authoritative detail (no ?name= on the route),
    // and the presence-delta count carries the approximate qualifier.
    expect(find.text('general'), findsOneWidget);
    expect(find.text('~1 online (estimate)'), findsOneWidget);

    // F3-R2: opening the room-info panel shows the same resolved title and
    // the estimate-labeled connected count.
    await tester.tap(find.byTooltip('Room info'));
    await tester.pumpAndSettle();
    expect(find.text('~1 connected — estimate'), findsOneWidget);
  });

  testWidgets('splits DM and group rooms from cache before the network returns',
      (tester) async {
    // F3-R4: kind + peer_username are persisted in the Drift cache, so a
    // relaunch renders the split from cache alone while the refresh is in
    // flight — the DM must never surface in the group list titled by its
    // internal auto-name.
    final gate = Completer<List<Room>>();
    final dm = Room(
      id: 2,
      name: 'dm-5-12',
      kind: 'dm',
      peerUsername: 'alice',
      createdAt: DateTime.utc(2026, 1, 2),
    );
    final group = Room(
      id: 1,
      name: 'general',
      createdAt: DateTime.utc(2026, 1, 1),
    );
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(listRoomsGate: gate),
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(rooms: [dm, group]),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Direct messages'), findsOneWidget);
    expect(find.text('alice'), findsOneWidget);
    expect(find.text('Group rooms'), findsOneWidget);
    expect(find.text('general'), findsOneWidget);
    // The internal DM auto-name is never displayed (F1-R7).
    expect(find.text('dm-5-12'), findsNothing);

    gate.complete(<Room>[group]);
    await tester.pumpAndSettle();
    expect(find.text('alice'), findsNothing);
    expect(find.text('general'), findsOneWidget);
  });

  testWidgets('sends a friend request by username from the friends pane', (
    tester,
  ) async {
    final friendsRepository = _FakeFriendsRepository();
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(),
        friendsRepository: friendsRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Friends'));
    await tester.pumpAndSettle();
    expect(find.text('No friends yet. Add someone by username.'), findsOneWidget);

    await tester.tap(find.byTooltip('Add a friend'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'bob');
    await tester.tap(find.text('Send request'));
    await tester.pumpAndSettle();

    expect(friendsRepository.sentUsernames, ['bob']);
    expect(find.text('Outgoing requests'), findsOneWidget);
    expect(find.text('bob'), findsOneWidget);
    expect(find.text('Pending'), findsOneWidget);
  });

  testWidgets('accepting an incoming request moves the peer into friends', (
    tester,
  ) async {
    final friendsRepository = _FakeFriendsRepository(
      incoming: [
        FriendRequest(
          id: 7,
          username: 'carol',
          createdAt: DateTime.utc(2026, 1, 1),
        ),
      ],
    );
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(),
        friendsRepository: friendsRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Friends'));
    await tester.pumpAndSettle();
    expect(find.text('Incoming requests'), findsOneWidget);
    expect(find.text('carol'), findsOneWidget);

    await tester.tap(find.byTooltip('Accept'));
    await tester.pumpAndSettle();

    expect(friendsRepository.acceptedUserId, 7);
    expect(find.text('carol'), findsOneWidget);
    expect(find.text('Direct message'), findsOneWidget);
  });

  testWidgets('decline removes an incoming request', (tester) async {
    final friendsRepository = _FakeFriendsRepository(
      incoming: [
        FriendRequest(
          id: 7,
          username: 'carol',
          createdAt: DateTime.utc(2026, 1, 1),
        ),
      ],
    );
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(),
        friendsRepository: friendsRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Friends'));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Decline'));
    await tester.pumpAndSettle();

    expect(friendsRepository.declinedUserId, 7);
    expect(find.text('carol'), findsNothing);
  });

  testWidgets('remove friend and unblock flows reach the repository', (
    tester,
  ) async {
    final friendsRepository = _FakeFriendsRepository(
      friends: [const Friend(id: 7, username: 'carol', roomId: 500)],
      blocked: [const Friend(id: 3, username: 'dave')],
    );
    await tester.pumpWidget(
      RelaywaveApp(
        authRepository: _FakeAuthenticatedRepository(),
        roomRepository: _FakeRoomRepository(),
        friendsRepository: friendsRepository,
        messageCache: _FakeMessageCache(),
        roomCache: _FakeRoomCache(),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Friends'));
    await tester.pumpAndSettle();
    expect(find.text('carol'), findsOneWidget);
    expect(find.text('Blocked'), findsOneWidget);
    expect(find.text('dave'), findsOneWidget);

    await tester.tap(find.byTooltip('Remove friend'));
    await tester.pumpAndSettle();
    expect(friendsRepository.removedUserId, 7);
    expect(find.text('carol'), findsNothing);

    await tester.tap(find.byTooltip('Unblock'));
    await tester.pumpAndSettle();
    expect(friendsRepository.unblockedUserId, 3);
    expect(find.text('dave'), findsNothing);
  });
}
