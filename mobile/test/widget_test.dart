import 'package:flutter_test/flutter_test.dart';

import 'package:relaywave_mobile/app/app.dart';
import 'package:relaywave_mobile/features/auth/domain/auth_repository.dart';
import 'package:relaywave_mobile/features/auth/domain/user.dart';
import 'package:relaywave_mobile/features/rooms/domain/room.dart';
import 'package:relaywave_mobile/features/rooms/domain/room_repository.dart';

class _FakeRoomRepository implements RoomRepository {
  @override
  Future<List<Room>> listRooms() => Future.value(const <Room>[]);

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

void main() {
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
}
