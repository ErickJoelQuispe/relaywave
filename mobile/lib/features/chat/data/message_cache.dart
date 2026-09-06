import '../../../core/database/app_database.dart';
import '../domain/message.dart';

abstract interface class MessageCache {
  Future<List<Message>> getRecentMessages(int roomId, {int limit = 100});
  Future<int?> getLastMessageId(int roomId);
  Future<void> save(Message message);
  Future<void> saveAll(Iterable<Message> messages);
  Future<void> clear();
}

final class DriftMessageCache implements MessageCache {
  DriftMessageCache(this._db);
  final AppDatabase _db;

  @override
  Future<List<Message>> getRecentMessages(int roomId, {int limit = 100}) async {
    // recentMessages returns DESC order (newest first); the bloc expects
    // ASCENDING (oldest first), so reverse the result.
    final rows = await _db.recentMessages(roomId, limit: limit);
    return rows.reversed.map(_toMessage).toList();
  }

  @override
  Future<int?> getLastMessageId(int roomId) => _db.lastMessageId(roomId);

  @override
  Future<void> save(Message message) => _db.saveMessage(_toRow(message));

  @override
  Future<void> saveAll(Iterable<Message> messages) =>
      _db.saveMessages(messages.map(_toRow));

  @override
  Future<void> clear() => _db.deleteAllMessages();

  Message _toMessage(MessageRow row) => Message(
        id: row.id,
        roomId: row.roomId,
        senderId: row.senderId,
        content: row.content,
        createdAt: row.createdAt,
      );

  MessageRow _toRow(Message message) => MessageRow(
        id: message.id,
        roomId: message.roomId,
        senderId: message.senderId,
        content: message.content,
        createdAt: message.createdAt,
      );
}
