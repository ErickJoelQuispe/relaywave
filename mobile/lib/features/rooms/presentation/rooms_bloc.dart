import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/network/api_exception.dart';
import '../data/room_cache.dart';
import '../domain/room.dart';
import '../domain/room_repository.dart';
import 'rooms_event.dart';
import 'rooms_state.dart';

final class RoomBloc extends Bloc<RoomsEvent, RoomsState> {
  RoomBloc(this._repository, {required RoomCache cache})
      : _cache = cache, // ignore: prefer_initializing_formals
        super(const RoomsInitial()) {
    on<RoomsLoadRequested>(_onLoad);
    on<RoomCreateRequested>(_onCreate);
    on<RoomJoinRequested>(_onJoin);
  }

  final RoomRepository _repository;
  final RoomCache _cache;

  Future<void> _onLoad(
    RoomsLoadRequested event,
    Emitter<RoomsState> emit,
  ) async {
    emit(const RoomsLoadInProgress());
    var cachedShown = false;
    try {
      final cached = await _cache.getRooms();
      if (cached.isNotEmpty) {
        emit(RoomsLoaded(rooms: cached));
        cachedShown = true;
      }
    } catch (_) {
      // Best-effort cache read; a miss or failure never blocks the fetch.
    }
    try {
      final rooms = await _repository.listRooms();
      unawaited(_cache.saveAll(rooms));
      emit(RoomsLoaded(rooms: rooms));
    } on ApiException catch (e) {
      if (cachedShown) return;
      emit(RoomsLoadFailure(e.message));
    } catch (_) {
      if (cachedShown) return;
      emit(const RoomsLoadFailure('Something went wrong. Please try again.'));
    }
  }

  Future<void> _onCreate(
    RoomCreateRequested event,
    Emitter<RoomsState> emit,
  ) async {
    // Creating a room does not depend on the cached list, so it must not be
    // gated on `state is RoomsLoaded` — the dialog that triggers this event
    // closes unconditionally, and skipping the API call here would silently
    // strand the user with a dialog that looked like it worked.
    final baseRooms = _roomsOf(state);
    emit(RoomsLoaded(rooms: baseRooms, submitting: true));
    try {
      final room = await _repository.createRoom(event.name);
      emit(RoomsLoaded(rooms: await _refreshedRooms(baseRooms, room)));
    } on ApiException catch (e) {
      emit(RoomsLoaded(rooms: baseRooms, error: e.message));
    } catch (_) {
      emit(
        RoomsLoaded(
          rooms: baseRooms,
          error: 'Something went wrong. Please try again.',
        ),
      );
    }
  }

  Future<void> _onJoin(
    RoomJoinRequested event,
    Emitter<RoomsState> emit,
  ) async {
    // See _onCreate: joining does not depend on the cached list either.
    final baseRooms = _roomsOf(state);
    emit(RoomsLoaded(rooms: baseRooms, submitting: true));
    try {
      final input = event.input.trim();
      final roomId = int.tryParse(input);
      if (roomId != null) {
        // All-numeric input takes the existing id-join path, unchanged
        // (F2-R5): joining a room the caller already belongs to still
        // surfaces the server's 409 "already a member".
        await _repository.joinRoom(roomId);
        emit(RoomsLoaded(rooms: await _refreshedRoomsOrFetch(baseRooms, roomId)));
      } else {
        // Free text: resolve the canonical slug to a room, then reuse the
        // same id-based join.
        final room = await _repository.getRoomByName(input);
        await _repository.joinRoom(room.id);
        emit(RoomsLoaded(rooms: await _refreshedRooms(baseRooms, room)));
      }
    } on ApiException catch (e) {
      emit(RoomsLoaded(rooms: baseRooms, error: e.message));
    } catch (_) {
      emit(
        RoomsLoaded(
          rooms: baseRooms,
          error: 'Something went wrong. Please try again.',
        ),
      );
    }
  }

  List<Room> _roomsOf(RoomsState state) =>
      state is RoomsLoaded ? state.rooms : const <Room>[];

  /// Refreshes the full list after a create. If the refresh fails, the room
  /// we just created is already known — merge it into `baseRooms` instead of
  /// silently dropping it from the UI while the membership still exists
  /// server-side.
  Future<List<Room>> _refreshedRooms(
    List<Room> baseRooms,
    Room newRoom,
  ) async {
    try {
      return await _repository.listRooms();
    } catch (_) {
      return _withRoom(baseRooms, newRoom);
    }
  }

  /// Same as [_refreshedRooms], but for a join: the join call only confirms
  /// membership, so on refresh failure we fetch the room's details directly
  /// rather than losing it from the list.
  Future<List<Room>> _refreshedRoomsOrFetch(
    List<Room> baseRooms,
    int roomId,
  ) async {
    try {
      return await _repository.listRooms();
    } catch (_) {
      final room = await _repository.getRoom(roomId);
      return _withRoom(baseRooms, room);
    }
  }

  List<Room> _withRoom(List<Room> rooms, Room room) {
    final merged = [...rooms];
    final index = merged.indexWhere((r) => r.id == room.id);
    if (index >= 0) {
      merged[index] = room;
    } else {
      merged.add(room);
    }
    return merged;
  }
}
