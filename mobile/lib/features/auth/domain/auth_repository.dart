import 'user.dart';

abstract interface class AuthRepository {
  Future<User> login(String email, String password);

  Future<User> register(String email, String username, String password);

  Future<void> logout();

  Future<User?> restoreSession();
}

final class AuthException implements Exception {
  const AuthException(this.message);

  final String message;
}
