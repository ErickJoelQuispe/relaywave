import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/network/api_exception.dart';
import '../domain/room_repository.dart';
import 'rooms_event.dart';
import 'rooms_state.dart';

final class RoomBloc extends Bloc<RoomsEvent, RoomsState> {
  RoomBloc(this._repository) : super(const RoomsInitial()) {
    on<RoomsLoadRequested>(_onLoad);
    on<RoomCreateRequested>(_onCreate);
    on<RoomJoinRequested>(_onJoin);
  }

  final RoomRepository _repository;

  Future<void> _onLoad(
    RoomsLoadRequested event,
    Emitter<RoomsState> emit,
  ) async {
    emit(const RoomsLoadInProgress());
    try {
      final rooms = await _repository.listRooms();
      emit(RoomsLoaded(rooms: rooms));
    } on ApiException catch (e) {
      emit(RoomsLoadFailure(e.message));
    } catch (_) {
      emit(const RoomsLoadFailure('Something went wrong. Please try again.'));
    }
  }

  Future<void> _onCreate(
    RoomCreateRequested event,
    Emitter<RoomsState> emit,
  ) async {
    final current = state;
    if (current is! RoomsLoaded) return;
    emit(RoomsLoaded(rooms: current.rooms, submitting: true));
    try {
      await _repository.createRoom(event.name);
      final rooms = await _repository.listRooms();
      emit(RoomsLoaded(rooms: rooms));
    } on ApiException catch (e) {
      emit(RoomsLoaded(rooms: current.rooms, error: e.message));
    } catch (_) {
      emit(
        RoomsLoaded(
          rooms: current.rooms,
          error: 'Something went wrong. Please try again.',
        ),
      );
    }
  }

  Future<void> _onJoin(
    RoomJoinRequested event,
    Emitter<RoomsState> emit,
  ) async {
    final current = state;
    if (current is! RoomsLoaded) return;
    emit(RoomsLoaded(rooms: current.rooms, submitting: true));
    try {
      await _repository.joinRoom(event.roomId);
      final rooms = await _repository.listRooms();
      emit(RoomsLoaded(rooms: rooms));
    } on ApiException catch (e) {
      emit(RoomsLoaded(rooms: current.rooms, error: e.message));
    } catch (_) {
      emit(
        RoomsLoaded(
          rooms: current.rooms,
          error: 'Something went wrong. Please try again.',
        ),
      );
    }
  }
}
