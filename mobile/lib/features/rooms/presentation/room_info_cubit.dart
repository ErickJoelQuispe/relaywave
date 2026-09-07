import 'package:flutter_bloc/flutter_bloc.dart';

import '../data/room_cache.dart';
import '../domain/room_repository.dart';
import 'room_info_state.dart';

/// Resolves the authoritative title/metadata for one room (F3-R1).
///
/// Chain: fresh `GET /rooms/{id}` detail → cached Drift row → the literal
/// `Room #id` placeholder. Provided above the chat view so the header title
/// and the room-info panel share a single source of truth. The cubit never
/// touches the WebSocket — presence stays in `ChatBloc` — so it only knows
/// what the REST detail endpoint and the cache say.
final class RoomInfoCubit extends Cubit<RoomInfoState> {
  RoomInfoCubit({
    required RoomRepository repository,
    required RoomCache cache,
    required int roomId,
  }) : _repository = repository, // ignore: prefer_initializing_formals
       _cache = cache, // ignore: prefer_initializing_formals
       _roomId = roomId, // ignore: prefer_initializing_formals
       super(const RoomInfoLoading());

  final RoomRepository _repository;
  final RoomCache _cache;
  final int _roomId;

  /// Fetch authoritative detail, falling back to the cache and then to the
  /// generic placeholder. Called when the chat screen opens.
  Future<void> load() async {
    emit(const RoomInfoLoading());
    try {
      final room = await _repository.getRoom(_roomId);
      if (!isClosed) emit(RoomInfoLoaded(room: room));
      return;
    } catch (_) {
      // Fall through to the cache; the fetch must never block the header.
    }
    try {
      final cached = await _cache.getRooms();
      final match = cached.where((room) => room.id == _roomId).firstOrNull;
      if (match != null) {
        if (!isClosed) emit(RoomInfoLoaded(room: match));
        return;
      }
    } catch (_) {
      // Best-effort cache read; a miss never blocks the placeholder.
    }
    if (!isClosed) emit(const RoomInfoMissing());
  }

  /// Re-fetch fresh detail when the room-info panel opens. A failure keeps
  /// the current state (previous detail, cached row, or placeholder) — the
  /// panel must not blank because a refresh failed.
  Future<void> refresh() async {
    try {
      final room = await _repository.getRoom(_roomId);
      if (!isClosed) emit(RoomInfoLoaded(room: room));
    } catch (_) {
      // Keep showing whatever we already had.
    }
  }
}
