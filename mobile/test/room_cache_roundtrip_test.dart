import 'package:drift/native.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:relaywave_mobile/core/database/app_database.dart';
import 'package:relaywave_mobile/features/rooms/data/room_cache.dart';
import 'package:relaywave_mobile/features/rooms/domain/room.dart';

void main() {
  late AppDatabase database;
  late DriftRoomCache cache;

  setUp(() {
    // In-memory sqlite: the v2 schema is created from the Drift table
    // definitions, exactly as a fresh install (or an upgraded one after the
    // v1 -> v2 migration) would see it.
    database = AppDatabase(executor: NativeDatabase.memory());
    cache = DriftRoomCache(database);
  });

  tearDown(() async {
    await database.close();
  });

  test('round-trips kind and peer_username through the Drift cache', () async {
    final group = Room(
      id: 1,
      name: 'project-alpha',
      kind: 'group',
      createdAt: DateTime.utc(2026, 1, 1),
    );
    final dm = Room(
      id: 2,
      name: 'dm-5-12', // internal auto-name, never displayed client-side
      kind: 'dm',
      peerUsername: 'alice',
      createdAt: DateTime.utc(2026, 1, 2),
    );

    await cache.saveAll([group, dm]);
    final loaded = await cache.getRooms();
    final byId = {for (final room in loaded) room.id: room};

    expect(byId, hasLength(2));
    expect(byId[1]!.kind, 'group');
    expect(byId[1]!.peerUsername, isNull);
    expect(byId[2]!.kind, 'dm');
    expect(byId[2]!.peerUsername, 'alice');
    // The split/title logic survives a relaunch from cache alone (F3-R4).
    expect(byId[2]!.displayTitle, 'alice');
  });

  test('kind defaults to group for rows written without it', () async {
    // The Rooms table declares kind with a constant default of 'group', so a
    // row written without an explicit kind (or backfilled by the v1 -> v2
    // migration, which adds the column with the same default) reads back as
    // a group room and renders in the group list, never the DM section.
    final raw = RoomRow(
      id: 7,
      name: 'legacy-room',
      createdBy: null,
      createdAt: DateTime.utc(2026, 1, 1),
      kind: 'group',
      peerUsername: null,
    );
    await database.saveRooms([raw]);

    final loaded = await cache.getRooms();
    expect(loaded.single.kind, 'group');
    expect(loaded.single.peerUsername, isNull);
  });
}
