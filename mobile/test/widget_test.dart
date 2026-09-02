import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:relaywave_mobile/app/app.dart';
import 'package:relaywave_mobile/features/auth/domain/auth_repository.dart';
import 'package:relaywave_mobile/features/auth/domain/user.dart';
import 'package:relaywave_mobile/features/chat/domain/chat_repository.dart';
import 'package:relaywave_mobile/features/chat/domain/message.dart';
import 'package:relaywave_mobile/features/rooms/domain/room.dart';
import 'package:relaywave_mobile/features/rooms/domain/room_repository.dart';

class _FakeRoomRepository implements RoomRepository {
  _FakeRoomRepository({this.rooms = const <Room>[]});

  final List<Room> rooms;

  @override
  Future<List<Room>> listRooms() async => rooms;

  @override
  Future<Room> createRoom(String name) {
    throw UnimplementedError();
  }

  @override
  Future<void> joinRoom(int roomId) {
    throw UnimplementedError();
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
  final StreamController<ChatSocketEvent> _controller =
      StreamController<ChatSocketEvent>.broadcast();

  void add(ChatSocketEvent event) => _controller.add(event);

  @override
  Future<ChatConnection> connect(int roomId) async {
    return _FakeChatConnection(_controller);
  }
}

void main() {
  final sampleRoom = Room(
    id: 1,
    name: 'general',
    createdAt: DateTime.utc(2026, 1, 1),
  );

  testWidgets('shows the login screen when unauthenticated', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(
      RelaywaveApp(authRepository: _FakeAuthRepository()),
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

    expect(find.text('hello world'), findsOneWidget);
  });
}
