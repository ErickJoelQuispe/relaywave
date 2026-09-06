import 'package:drift/drift.dart';
import 'package:drift_flutter/drift_flutter.dart';

part 'app_database.g.dart';

@DataClassName('MessageRow') // avoids collision with the domain `Message` class
class Messages extends Table {
  IntColumn get id => integer()();
  IntColumn get roomId => integer().named('room_id')();
  IntColumn get senderId => integer().named('sender_id')();
  TextColumn get content => text()();
  DateTimeColumn get createdAt => dateTime().named('created_at')();

  @override
  Set<Column> get primaryKey => {id};
}

@DataClassName('RoomRow')
class Rooms extends Table {
  IntColumn get id => integer()();
  TextColumn get name => text()();
  IntColumn get createdBy => integer().nullable().named('created_by')();
  DateTimeColumn get createdAt => dateTime().named('created_at')();

  @override
  Set<Column> get primaryKey => {id};
}

@DriftDatabase(tables: [Messages, Rooms])
class AppDatabase extends _$AppDatabase {
  // `web:` is required when this app runs as Flutter Web: drift loads sqlite3
  // compiled to WebAssembly plus a background worker instead of a native file.
  // Both assets are downloaded into mobile/web/ (matching the pinned `drift`
  // version in pubspec.lock) since they aren't fetched at build time.
  AppDatabase()
    : super(
        driftDatabase(
          name: 'relaywave',
          web: DriftWebOptions(
            sqlite3Wasm: Uri.parse('sqlite3.wasm'),
            driftWorker: Uri.parse('drift_worker.js'),
          ),
        ),
      );

  @override
  int get schemaVersion => 1;

  Future<List<MessageRow>> recentMessages(int roomId, {int limit = 100}) =>
      (select(messages)
            ..where((m) => m.roomId.equals(roomId))
            ..orderBy([(m) => OrderingTerm.desc(m.id)])
            ..limit(limit))
          .get();

  Future<int?> lastMessageId(int roomId) async {
    final query = selectOnly(messages)
      ..addColumns([messages.id.max()])
      ..where(messages.roomId.equals(roomId));
    final row = await query.getSingleOrNull();
    return row?.read(messages.id.max());
  }

  Future<void> saveMessage(MessageRow row) =>
      into(messages).insertOnConflictUpdate(row);

  Future<void> saveMessages(Iterable<MessageRow> rows) =>
      batch((b) => b.insertAll(messages, rows, mode: InsertMode.insertOrReplace));

  Future<List<RoomRow>> allRooms() =>
      (select(rooms)..orderBy([(r) => OrderingTerm.asc(r.id)])).get();

  Future<void> saveRooms(Iterable<RoomRow> rows) =>
      batch((b) => b.insertAll(rooms, rows, mode: InsertMode.insertOrReplace));

  Future<void> deleteAllRooms() => delete(rooms).go();

  Future<void> deleteAllMessages() => delete(messages).go();
}
