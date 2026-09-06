import '../../../core/database/app_database.dart';
import '../domain/room.dart';

abstract interface class RoomCache {
  Future<List<Room>> getRooms();
  Future<void> saveAll(Iterable<Room> rooms);
  Future<void> clear();
}

final class DriftRoomCache implements RoomCache {
  DriftRoomCache(this._db);
  final AppDatabase _db;

  @override
  Future<List<Room>> getRooms() async {
    final rows = await _db.allRooms();
    return rows.map(_toRoom).toList();
  }

  @override
  Future<void> saveAll(Iterable<Room> rooms) =>
      _db.saveRooms(rooms.map(_toRow));

  @override
  Future<void> clear() => _db.deleteAllRooms();

  Room _toRoom(RoomRow row) => Room(
        id: row.id,
        name: row.name,
        createdBy: row.createdBy,
        createdAt: row.createdAt,
      );

  RoomRow _toRow(Room room) => RoomRow(
        id: room.id,
        name: room.name,
        createdBy: room.createdBy,
        createdAt: room.createdAt,
      );
}
