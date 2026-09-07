import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:relaywave_mobile/features/rooms/data/room_cache.dart';
import 'package:relaywave_mobile/features/rooms/domain/room.dart';
import 'package:relaywave_mobile/features/rooms/domain/room_repository.dart';
import 'package:relaywave_mobile/features/rooms/presentation/room_info_cubit.dart';
import 'package:relaywave_mobile/features/rooms/presentation/room_info_panel.dart';

class _StubRoomRepository implements RoomRepository {
  _StubRoomRepository({this.detail});

  final Room? detail;

  @override
  Future<Room> getRoom(int roomId) async {
    final room = detail;
    if (room == null) throw StateError('no detail');
    return room;
  }

  @override
  Future<List<Room>> listRooms() async => const [];

  @override
  Future<Room> createRoom(String name) => throw UnimplementedError();

  @override
  Future<Room> getRoomByName(String name) => throw UnimplementedError();

  @override
  Future<void> joinRoom(int roomId) async {}
}

class _StubRoomCache implements RoomCache {
  _StubRoomCache({List<Room> rooms = const <Room>[]}) : rooms = List.of(rooms);

  final List<Room> rooms;

  @override
  Future<List<Room>> getRooms() async => List.of(rooms);

  @override
  Future<void> saveAll(Iterable<Room> rooms) async {}

  @override
  Future<void> clear() async {}
}

Future<RoomInfoCubit> _pumpPanel(
  WidgetTester tester, {
  required RoomRepository repository,
  required RoomCache cache,
  int? onlineCount = 3,
}) async {
  final cubit = RoomInfoCubit(
    repository: repository,
    cache: cache,
    roomId: 1,
  )..load();
  addTearDown(cubit.close);

  await tester.pumpWidget(
    MaterialApp(
      home: Scaffold(
        body: BlocProvider<RoomInfoCubit>.value(
          value: cubit,
          child: RoomInfoPanel(roomId: 1, onlineCount: onlineCount),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
  return cubit;
}

void main() {
  final groupDetail = Room(
    id: 1,
    name: 'project-alpha',
    kind: 'group',
    capacity: 10,
    createdAt: DateTime.utc(2026, 1, 1),
  );

  testWidgets('panel renders title, approximate count and capacity', (
    tester,
  ) async {
    await _pumpPanel(
      tester,
      repository: _StubRoomRepository(detail: groupDetail),
      cache: _StubRoomCache(),
      onlineCount: 3,
    );

    expect(find.text('project-alpha'), findsWidgets); // title + slug subtitle
    expect(find.text('~3 connected — estimate'), findsOneWidget);
    expect(find.text('Capacity: 10'), findsOneWidget);
  });

  testWidgets('panel shows the generic placeholder when detail and cache miss',
      (tester) async {
    await _pumpPanel(
      tester,
      repository: _StubRoomRepository(),
      cache: _StubRoomCache(),
    );

    // F3-R1: never a fabricated name — both title and footer fall back to
    // the generic Room #id.
    expect(find.text('Room #1'), findsWidgets);
    expect(find.text('~3 connected — estimate'), findsOneWidget);
  });

  testWidgets('panel titles a DM from the cached peer username (F1-R7)', (
    tester,
  ) async {
    final dm = Room(
      id: 1,
      name: 'dm-5-12',
      kind: 'dm',
      peerUsername: 'alice',
      createdAt: DateTime.utc(2026, 1, 1),
    );
    await _pumpPanel(
      tester,
      repository: _StubRoomRepository(), // detail fetch fails
      cache: _StubRoomCache(rooms: [dm]),
    );

    // Title from the cached peer; the internal auto-name never appears and
    // no capacity row shows for a DM.
    expect(find.text('alice'), findsOneWidget);
    expect(find.text('dm-5-12'), findsNothing);
    expect(find.textContaining('Capacity'), findsNothing);
  });

  testWidgets('panel omits the estimate row when no socket count exists', (
    tester,
  ) async {
    await _pumpPanel(
      tester,
      repository: _StubRoomRepository(detail: groupDetail),
      cache: _StubRoomCache(),
      onlineCount: null, // connection not active (ChatConnecting/Failed)
    );

    expect(find.textContaining('estimate'), findsNothing);
  });
}
