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
  const RoomJoinRequested(this.input);

  /// Raw join input: a numeric room id or free text naming a room (F2-R5).
  final String input;
  @override
  List<Object?> get props => [input];
}
