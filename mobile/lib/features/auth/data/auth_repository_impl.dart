import 'package:dio/dio.dart';

import '../../../core/network/api_exception.dart';
import '../../chat/data/message_cache.dart';
import '../../rooms/data/room_cache.dart';
import '../domain/auth_repository.dart';
import '../domain/user.dart';
import 'token_storage.dart';

final class AuthRepositoryImpl implements AuthRepository {
  AuthRepositoryImpl({
    required Dio dio,
    required TokenStorage tokenStorage,
    required RoomCache roomCache,
    required MessageCache messageCache,
  })  : _dio = dio, // ignore: prefer_initializing_formals
        _tokenStorage = tokenStorage, // ignore: prefer_initializing_formals
        _roomCache = roomCache, // ignore: prefer_initializing_formals
        _messageCache = messageCache; // ignore: prefer_initializing_formals

  final Dio _dio;
  final TokenStorage _tokenStorage;
  final RoomCache _roomCache;
  final MessageCache _messageCache;

  @override
  Future<User> login(String email, String password) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/auth/login',
        data: {'email': email, 'password': password},
      );
      final data = response.data!;
      await _tokenStorage.writeTokens(
        access: data['access_token'] as String,
        refresh: data['refresh_token'] as String,
      );
      return await _fetchMe();
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
  }

  @override
  Future<User> register(String email, String username, String password) async {
    try {
      await _dio.post<Map<String, dynamic>>(
        '/auth/register',
        data: {'email': email, 'username': username, 'password': password},
      );
    } on DioException catch (e) {
      throw ApiException(dioErrorMessage(e));
    }
    return login(email, password);
  }

  @override
  Future<void> logout() async {
    final refresh = await _tokenStorage.readRefreshToken();
    if (refresh != null && refresh.isNotEmpty) {
      try {
        await _dio.post<void>(
          '/auth/logout',
          data: {'refresh_token': refresh},
        );
      } on DioException {
        // Best-effort: the remote revoke may fail, but local logout must proceed.
      }
    }
    // Clear local caches alongside the tokens so a subsequent login on the
    // same app instance never briefly flashes the previous account's data.
    await _tokenStorage.clear();
    await _roomCache.clear();
    await _messageCache.clear();
  }

  @override
  Future<User?> restoreSession() async {
    final access = await _tokenStorage.readAccessToken();
    final refresh = await _tokenStorage.readRefreshToken();
    if (access == null || refresh == null) {
      return null;
    }

    try {
      return await _fetchMe();
    } on DioException catch (e) {
      if (e.response?.statusCode != 401) {
        return null;
      }
      return _refreshSession(refresh);
    }
  }

  Future<User> _fetchMe() async {
    final response = await _dio.get<Map<String, dynamic>>('/auth/me');
    return User.fromJson(response.data!);
  }

  Future<User?> _refreshSession(String refresh) async {
    try {
      final response = await _dio.post<Map<String, dynamic>>(
        '/auth/refresh',
        data: {'refresh_token': refresh},
      );
      final data = response.data!;
      await _tokenStorage.writeTokens(
        access: data['access_token'] as String,
        refresh: data['refresh_token'] as String,
      );
      return await _fetchMe();
    } on DioException {
      await _tokenStorage.clear();
      return null;
    }
  }
}
