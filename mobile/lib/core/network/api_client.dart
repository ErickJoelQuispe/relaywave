import 'package:dio/dio.dart';

import '../../features/auth/data/token_storage.dart';
import '../config/app_config.dart';

final class ApiClient {
  ApiClient({required TokenStorage tokenStorage}) {
    dio = Dio(BaseOptions(baseUrl: AppConfig.apiBaseUrl));
    dio.interceptors.add(AuthInterceptor(tokenStorage));
  }

  late final Dio dio;
}

final class AuthInterceptor extends Interceptor {
  AuthInterceptor(this._tokenStorage);

  final TokenStorage _tokenStorage;

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    final token = await _tokenStorage.readAccessToken();
    if (token != null && token.isNotEmpty) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(options);
  }
}
