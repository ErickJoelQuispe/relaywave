import 'room.dart';

abstract interface class RoomRepository {
  Future<List<Room>> listRooms();
  Future<Room> createRoom(String name);
  Future<Room> getRoom(int roomId);
  Future<void> joinRoom(int roomId);
}
