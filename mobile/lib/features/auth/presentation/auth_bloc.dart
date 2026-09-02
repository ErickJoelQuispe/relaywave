import 'package:flutter_bloc/flutter_bloc.dart';

import '../domain/auth_repository.dart';
import 'auth_event.dart';
import 'auth_state.dart';

final class AuthBloc extends Bloc<AuthEvent, AuthState> {
  AuthBloc(this._repository) : super(const AuthUnknown()) {
    on<AuthCheckRequested>(_onCheck);
    on<AuthLoginRequested>(_onLogin);
    on<AuthRegisterRequested>(_onRegister);
    on<AuthLogoutRequested>(_onLogout);
  }

  final AuthRepository _repository;

  Future<void> _onCheck(
    AuthCheckRequested event,
    Emitter<AuthState> emit,
  ) async {
    try {
      final user = await _repository.restoreSession();
      if (isClosed) return;
      emit(user != null ? AuthAuthenticated(user) : const AuthUnauthenticated());
    } catch (_) {
      // A storage/network failure during restore must not crash startup:
      // fall back to "not authenticated" and let the user log in again.
      if (isClosed) return;
      emit(const AuthUnauthenticated());
    }
  }

  Future<void> _onLogin(
    AuthLoginRequested event,
    Emitter<AuthState> emit,
  ) async {
    emit(const AuthLoading());
    try {
      final user = await _repository.login(event.email, event.password);
      emit(AuthAuthenticated(user));
    } on AuthException catch (e) {
      emit(AuthUnauthenticated(errorMessage: e.message));
    } catch (_) {
      emit(const AuthUnauthenticated(
        errorMessage: 'Something went wrong. Please try again.',
      ));
    }
  }

  Future<void> _onRegister(
    AuthRegisterRequested event,
    Emitter<AuthState> emit,
  ) async {
    emit(const AuthLoading());
    try {
      final user = await _repository.register(
        event.email,
        event.username,
        event.password,
      );
      emit(AuthAuthenticated(user));
    } on AuthException catch (e) {
      emit(AuthUnauthenticated(errorMessage: e.message));
    } catch (_) {
      emit(const AuthUnauthenticated(
        errorMessage: 'Something went wrong. Please try again.',
      ));
    }
  }

  Future<void> _onLogout(
    AuthLogoutRequested event,
    Emitter<AuthState> emit,
  ) async {
    await _repository.logout();
    emit(const AuthUnauthenticated());
  }
}
