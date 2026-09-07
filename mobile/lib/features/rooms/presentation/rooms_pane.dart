import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../../auth/presentation/auth_bloc.dart';
import '../../auth/presentation/auth_event.dart';
import '../../../core/widgets/shimmer_list_placeholder.dart';
import '../domain/room.dart';
import 'rooms_bloc.dart';
import 'rooms_event.dart';
import 'rooms_state.dart';

class RoomsPane extends StatefulWidget {
  const RoomsPane({super.key});

  @override
  State<RoomsPane> createState() => _RoomsPaneState();
}

class _RoomsPaneState extends State<RoomsPane> {
  bool _roomsAnimatedOnce = false;

  @override
  void initState() {
    super.initState();
    context.read<RoomBloc>().add(const RoomsLoadRequested());
  }

  // Dialog content lives in its own StatefulWidget (_JoinRoomDialog /
  // _CreateRoomDialog below) so the TextEditingController is created and
  // disposed by the framework's own element lifecycle. Manually creating a
  // controller here and calling `controller.dispose()` right after `await
  // showDialog(...)` races the dialog's exit transition: `Navigator.pop()`
  // resolves that future before the route finishes animating out, so the
  // still-rendering TextField could touch the controller after dispose,
  // throwing "A TextEditingController was used after being disposed."
  Future<void> _showJoinRoomDialog() async {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => _JoinRoomDialog(
        onSubmit: (input) {
          context.read<RoomBloc>().add(RoomJoinRequested(input));
          Navigator.of(dialogContext).pop();
        },
      ),
    );
  }

  Future<void> _showCreateRoomDialog() async {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => _CreateRoomDialog(
        onSubmit: (name) {
          context.read<RoomBloc>().add(RoomCreateRequested(name));
          Navigator.of(dialogContext).pop();
        },
      ),
    );
  }

  Future<void> _copyRoomName(String name) async {
    await Clipboard.setData(ClipboardData(text: name));
    if (!mounted) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text('Room name "$name" copied')));
  }

  Widget _buildBody(RoomsState state) {
    return switch (state) {
      RoomsInitial() || RoomsLoadInProgress() =>
        const ShimmerListPlaceholder(),
      RoomsLoadFailure(:final message) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(message, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              OutlinedButton(
                onPressed: () =>
                    context.read<RoomBloc>().add(const RoomsLoadRequested()),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      RoomsLoaded(:final rooms, :final submitting) => _buildLoaded(
          rooms,
          submitting,
        ),
    };
  }

  Widget _buildLoaded(List<Room> rooms, bool submitting) {
    // The rooms list staggers in once the first time a non-empty list renders.
    // Later rebuilds (including the stale-while-revalidate refresh) render
    // with no animation wrapper.
    final shouldAnimate = !_roomsAnimatedOnce && rooms.isNotEmpty;
    if (shouldAnimate) _roomsAnimatedOnce = true;

    return Column(
      children: [
        if (submitting) const LinearProgressIndicator(),
        Expanded(
          child: rooms.isEmpty
              ? const Center(
                  child: Text('No rooms yet. Create or join one.'),
                )
              : ListView.builder(
                  itemCount: rooms.length,
                  itemBuilder: (context, index) {
                    // The canonical slug IS the shareable handle (F2-R5);
                    // copying it is the invite affordance.
                    final tile = ListTile(
                      title: Text(rooms[index].displayTitle),
                      onTap: () => context.go('/rooms/${rooms[index].id}'),
                      trailing: IconButton(
                        icon: const Icon(Icons.copy_outlined, size: 18),
                        tooltip: 'Copy room name to invite others',
                        onPressed: () => _copyRoomName(rooms[index].name),
                      ),
                    );
                    if (!shouldAnimate) return tile;
                    return tile
                        .animate(delay: (30 * index).clamp(0, 250).ms)
                        .fadeIn(
                          duration: 200.ms,
                          curve: Curves.easeOut,
                        )
                        .slideX(
                          begin: 0.05,
                          end: 0,
                          duration: 200.ms,
                          curve: Curves.easeOut,
                        );
                  },
                ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return BlocListener<RoomBloc, RoomsState>(
      listener: (context, state) {
        final error = switch (state) {
          RoomsLoaded(:final error) => error,
          _ => null,
        };
        if (error != null) {
          ScaffoldMessenger.of(context)
            ..hideCurrentSnackBar()
            ..showSnackBar(SnackBar(content: Text(error)));
        }
      },
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Rooms'),
          actions: [
            IconButton(
              icon: const Icon(Icons.group_add_outlined),
              tooltip: 'Join a room',
              onPressed: _showJoinRoomDialog,
            ),
            IconButton(
              icon: const Icon(Icons.logout),
              tooltip: 'Log out',
              onPressed: () =>
                  context.read<AuthBloc>().add(const AuthLogoutRequested()),
            ),
          ],
        ),
        body: BlocBuilder<RoomBloc, RoomsState>(
          builder: (context, state) => _buildBody(state),
        ),
        floatingActionButton: FloatingActionButton(
          tooltip: 'Create room',
          onPressed: _showCreateRoomDialog,
          child: const Icon(Icons.add),
        ),
      ),
    );
  }
}

class _JoinRoomDialog extends StatefulWidget {
  const _JoinRoomDialog({required this.onSubmit});

  final ValueChanged<String> onSubmit;

  @override
  State<_JoinRoomDialog> createState() => _JoinRoomDialogState();
}

class _JoinRoomDialogState extends State<_JoinRoomDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final input = _controller.text.trim();
    if (input.isEmpty) return;
    widget.onSubmit(input);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Join a room'),
      content: TextField(
        controller: _controller,
        autofocus: true,
        decoration: const InputDecoration(
          labelText: 'Room ID or name',
          border: OutlineInputBorder(),
        ),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _submit,
          child: const Text('Join'),
        ),
      ],
    );
  }
}

class _CreateRoomDialog extends StatefulWidget {
  const _CreateRoomDialog({required this.onSubmit});

  final ValueChanged<String> onSubmit;

  @override
  State<_CreateRoomDialog> createState() => _CreateRoomDialogState();
}

class _CreateRoomDialogState extends State<_CreateRoomDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final name = _controller.text.trim();
    if (name.isEmpty) return;
    widget.onSubmit(name);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Create room'),
      content: TextField(
        controller: _controller,
        autofocus: true,
        decoration: const InputDecoration(
          labelText: 'Room name',
          border: OutlineInputBorder(),
        ),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _submit,
          child: const Text('Create'),
        ),
      ],
    );
  }
}
