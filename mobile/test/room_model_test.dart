import 'package:flutter_test/flutter_test.dart';

import 'package:relaywave_mobile/features/rooms/domain/room.dart';

void main() {
  group('Room.fromJson', () {
    test('parses detail fields end to end, dropping nothing (F3-R4)', () {
      final room = Room.fromJson({
        'id': 42,
        'name': 'dm-5-12',
        'created_by': null,
        'created_at': '2026-01-01T00:00:00Z',
        'kind': 'dm',
        'capacity': null,
        'peer_username': 'alice',
        'member_count': 2,
      });

      expect(room.id, 42);
      expect(room.kind, 'dm');
      expect(room.capacity, isNull);
      expect(room.peerUsername, 'alice');
      expect(room.memberCount, 2);
    });

    test('list rows default missing fields (kind=group, null metadata)', () {
      // GET /rooms list payloads carry kind + peer_username but no
      // capacity/member_count.
      final room = Room.fromJson({
        'id': 7,
        'name': 'project-alpha',
        'created_by': 1,
        'created_at': '2026-01-01T00:00:00Z',
        'kind': 'group',
        'peer_username': null,
      });

      expect(room.kind, 'group');
      expect(room.peerUsername, isNull);
      expect(room.capacity, isNull);
      expect(room.memberCount, isNull);
    });

    test('tolerates a legacy payload with no kind at all', () {
      final room = Room.fromJson({
        'id': 1,
        'name': 'legacy',
        'created_by': 1,
        'created_at': '2026-01-01T00:00:00Z',
      });
      expect(room.kind, 'group');
    });
  });

  group('Room.displayTitle', () {
    test('DM rooms title from the peer username, never the auto-name', () {
      final dm = Room(
        id: 2,
        name: 'dm-5-12',
        kind: 'dm',
        peerUsername: 'alice',
        createdAt: DateTime.utc(2026, 1, 1),
      );
      expect(dm.displayTitle, 'alice');
    });

    test('group rooms title from the canonical slug', () {
      final group = Room(
        id: 1,
        name: 'project-alpha',
        createdAt: DateTime.utc(2026, 1, 1),
      );
      expect(group.displayTitle, 'project-alpha');
    });
  });
}
