import 'package:equatable/equatable.dart';
import '../domain/room.dart';

sealed class RoomsState extends Equatable {
  const RoomsState();
}

final class RoomsInitial extends RoomsState {
  const RoomsInitial();
  @override
  List<Object?> get props => const [];
}

final class RoomsLoadInProgress extends RoomsState {
  const RoomsLoadInProgress();
  @override
  List<Object?> get props => const [];
}

final class RoomsLoaded extends RoomsState {
  const RoomsLoaded({required this.rooms, this.submitting = false, this.error});
  final List<Room> rooms;
  final bool submitting;
  final String? error;
  @override
  List<Object?> get props => [rooms, submitting, error];
}

final class RoomsLoadFailure extends RoomsState {
  const RoomsLoadFailure(this.message);
  final String message;
  @override
  List<Object?> get props => [message];
}
