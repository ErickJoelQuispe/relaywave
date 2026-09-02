import 'package:equatable/equatable.dart';

sealed class RoomsEvent extends Equatable {
  const RoomsEvent();
  @override
  List<Object?> get props => const [];
}

final class RoomsLoadRequested extends RoomsEvent {
  const RoomsLoadRequested();
}

final class RoomCreateRequested extends RoomsEvent {
  const RoomCreateRequested(this.name);
  final String name;
  @override
  List<Object?> get props => [name];
}

final class RoomJoinRequested extends RoomsEvent {
  const RoomJoinRequested(this.roomId);
  final int roomId;
  @override
  List<Object?> get props => [roomId];
}
