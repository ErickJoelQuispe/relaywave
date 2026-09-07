import 'package:dio/dio.dart';

import '../../../core/network/api_exception.dart';
import '../domain/room.dart';
import '../domain/room_repository.dart';

final class RoomRepositoryImpl implements RoomRepository {
  RoomRepositoryImpl({required Dio dio}) : _dio = dio; // ignore: prefer_initializing_formals

  final Dio _dio;

  @override
  Future<List<Room>> listRooms() async {
    try {
      final response = await _dio.get<List<dynamic>>('/rooms');
      final data = response.data ?? const <dynamic>[];
      return data
          .map((item) => Room.fromJson(item as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<Room> createRoom(String name) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/rooms',
        data: {'name': name},
      );
      return Room.fromJson(response.data!);
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<Room> getRoom(int roomId) async {
    try {
      final response = await _dio.get<Map<String, dynamic>>('/rooms/$roomId');
      return Room.fromJson(response.data!);
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<Room> getRoomByName(String name) async {
    try {
      // The server canonicalizes the raw text into the room slug (F2-R2);
      // the client only needs to make it a valid path segment. Encode so
      // free text like "Project Alpha!" survives the trip unchanged.
      final encoded = Uri.encodeComponent(name);
      final response = await _dio.get<Map<String, dynamic>>(
        '/rooms/by-name/$encoded',
      );
      return Room.fromJson(response.data!);
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<void> joinRoom(int roomId) async {
    try {
      await _dio.post<void>('/rooms/$roomId/join');
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }
}
