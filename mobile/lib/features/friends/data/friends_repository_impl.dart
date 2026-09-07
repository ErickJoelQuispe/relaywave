import 'package:dio/dio.dart';

import '../../../core/network/api_exception.dart';
import '../../rooms/domain/room.dart';
import '../domain/friend.dart';
import '../domain/friends_repository.dart';

final class FriendsRepositoryImpl implements FriendsRepository {
  FriendsRepositoryImpl({required Dio dio}) : _dio = dio; // ignore: prefer_initializing_formals

  final Dio _dio;

  @override
  Future<void> sendRequest(String username) async {
    try {
      await _dio.post<void>(
        '/friends/requests',
        data: {'username': username},
      );
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<List<FriendRequest>> listRequests({
    required String direction,
  }) async {
    try {
      final response = await _dio.get<List<dynamic>>(
        '/friends/requests',
        queryParameters: {'direction': direction},
      );
      final data = response.data ?? const <dynamic>[];
      return data
          .map((item) => FriendRequest.fromJson(item as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<Room> acceptRequest(int userId) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/friends/requests/$userId/accept',
      );
      final data = response.data!;
      return Room.fromJson(data['room'] as Map<String, dynamic>);
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<void> declineRequest(int userId) async {
    try {
      await _dio.delete<void>('/friends/requests/$userId');
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<List<Friend>> listFriends() async {
    try {
      final response = await _dio.get<List<dynamic>>('/friends');
      final data = response.data ?? const <dynamic>[];
      return data
          .map((item) => Friend.fromJson(item as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<void> removeFriend(int userId) async {
    try {
      await _dio.delete<void>('/friends/$userId');
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<void> block(int userId) async {
    try {
      await _dio.post<void>('/friends/blocks', data: {'user_id': userId});
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<List<Friend>> listBlocked() async {
    try {
      final response = await _dio.get<List<dynamic>>('/friends/blocks');
      final data = response.data ?? const <dynamic>[];
      return data
          .map((item) => Friend.fromJson(item as Map<String, dynamic>))
          .toList();
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<void> unblock(int userId) async {
    try {
      await _dio.delete<void>('/friends/blocks/$userId');
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }
}
