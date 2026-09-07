import 'package:equatable/equatable.dart';

import '../../rooms/domain/room.dart';

sealed class RoomInfoState extends Equatable {
  const RoomInfoState();

  @override
  List<Object?> get props => const [];
}

/// Initial fetch in flight (chat screen opened).
final class RoomInfoLoading extends RoomInfoState {
  const RoomInfoLoading();
}

/// A title source is available: fresh server detail, or the cached Drift row
/// when the fetch failed (F3-R1). Callers render the generic `Room #id`
/// placeholder instead when the state is [RoomInfoMissing].
final class RoomInfoLoaded extends RoomInfoState {
  const RoomInfoLoaded({required this.room});

  final Room room;

  @override
  List<Object?> get props => [room];
}

/// Neither the detail fetch nor the cache produced a row: show the generic
/// `Room #id` placeholder, never a fabricated name (F3-R1).
final class RoomInfoMissing extends RoomInfoState {
  const RoomInfoMissing();
}
