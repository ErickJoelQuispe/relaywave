import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/network/api_exception.dart';
import '../domain/friends_repository.dart';
import 'friends_event.dart';
import 'friends_state.dart';

/// Drives every relationship surface: friends, incoming/outgoing requests,
/// and the blocked list (F1-R7).
///
/// Each mutation refreshes all four lists so the sections stay consistent —
/// e.g. accepting an incoming request moves the peer from `incoming` into
/// `friends` in one refresh. Errors surface through the state's `error`
/// field; the pane shows them in a snackbar.
final class FriendsBloc extends Bloc<FriendsEvent, FriendsState> {
  FriendsBloc(this._repository) : super(const FriendsInitial()) {
    on<FriendsLoadRequested>(_onLoad);
    on<FriendAddRequested>(_onSend);
    on<FriendAcceptRequested>(_onAccept);
    on<FriendDeclineRequested>(_onDecline);
    on<FriendRemoveRequested>(_onRemove);
    on<FriendUnblockRequested>(_onUnblock);
  }

  final FriendsRepository _repository;

  Future<void> _onLoad(
    FriendsLoadRequested event,
    Emitter<FriendsState> emit,
  ) async {
    emit(const FriendsLoadInProgress());
    await _refresh(emit);
  }

  Future<void> _onSend(
    FriendAddRequested event,
    Emitter<FriendsState> emit,
  ) async {
    final base = _baseOf(state);
    emit(base.copyWith(submitting: true));
    try {
      await _repository.sendRequest(event.username);
      await _refresh(emit);
    } on ApiException catch (e) {
      emit(base.copyWith(error: e.message));
    } catch (_) {
      emit(base.copyWith(error: 'Something went wrong. Please try again.'));
    }
  }

  Future<void> _onAccept(
    FriendAcceptRequested event,
    Emitter<FriendsState> emit,
  ) async {
    final base = _baseOf(state);
    emit(base.copyWith(submitting: true));
    try {
      await _repository.acceptRequest(event.userId);
      await _refresh(emit);
    } on ApiException catch (e) {
      emit(base.copyWith(error: e.message));
    } catch (_) {
      emit(base.copyWith(error: 'Something went wrong. Please try again.'));
    }
  }

  Future<void> _onDecline(
    FriendDeclineRequested event,
    Emitter<FriendsState> emit,
  ) async {
    final base = _baseOf(state);
    emit(base.copyWith(submitting: true));
    try {
      await _repository.declineRequest(event.userId);
      await _refresh(emit);
    } on ApiException catch (e) {
      emit(base.copyWith(error: e.message));
    } catch (_) {
      emit(base.copyWith(error: 'Something went wrong. Please try again.'));
    }
  }

  Future<void> _onRemove(
    FriendRemoveRequested event,
    Emitter<FriendsState> emit,
  ) async {
    final base = _baseOf(state);
    emit(base.copyWith(submitting: true));
    try {
      await _repository.removeFriend(event.userId);
      await _refresh(emit);
    } on ApiException catch (e) {
      emit(base.copyWith(error: e.message));
    } catch (_) {
      emit(base.copyWith(error: 'Something went wrong. Please try again.'));
    }
  }

  Future<void> _onUnblock(
    FriendUnblockRequested event,
    Emitter<FriendsState> emit,
  ) async {
    final base = _baseOf(state);
    emit(base.copyWith(submitting: true));
    try {
      await _repository.unblock(event.userId);
      await _refresh(emit);
    } on ApiException catch (e) {
      emit(base.copyWith(error: e.message));
    } catch (_) {
      emit(base.copyWith(error: 'Something went wrong. Please try again.'));
    }
  }

  Future<void> _refresh(Emitter<FriendsState> emit) async {
    if (isClosed) return;
    emit(const FriendsLoadInProgress());
    try {
      // Start all four fetches, then await each: parallel network calls with
      // fully typed results (Future.wait would collapse the generics).
      final friendsFuture = _repository.listFriends();
      final incomingFuture = _repository.listRequests(direction: 'incoming');
      final outgoingFuture = _repository.listRequests(direction: 'outgoing');
      final blockedFuture = _repository.listBlocked();
      final friends = await friendsFuture;
      final incoming = await incomingFuture;
      final outgoing = await outgoingFuture;
      final blocked = await blockedFuture;
      if (isClosed || emit.isDone) return;
      emit(
        FriendsLoaded(
          friends: friends,
          incoming: incoming,
          outgoing: outgoing,
          blocked: blocked,
        ),
      );
    } on ApiException catch (e) {
      if (isClosed || emit.isDone) return;
      emit(FriendsLoadFailure(e.message));
    } catch (_) {
      if (isClosed || emit.isDone) return;
      emit(const FriendsLoadFailure('Something went wrong. Please try again.'));
    }
  }

  FriendsLoaded _baseOf(FriendsState state) => state is FriendsLoaded
      ? state
      : const FriendsLoaded(
          friends: [],
          incoming: [],
          outgoing: [],
          blocked: [],
        );
}
