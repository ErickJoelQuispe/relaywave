import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../../auth/presentation/auth_bloc.dart';
import '../../auth/presentation/auth_event.dart';
import 'rooms_bloc.dart';
import 'rooms_event.dart';
import 'rooms_state.dart';

class RoomsPane extends StatefulWidget {
  const RoomsPane({super.key});

  @override
  State<RoomsPane> createState() => _RoomsPaneState();
}

class _RoomsPaneState extends State<RoomsPane> {
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
        onSubmit: (id) {
          context.read<RoomBloc>().add(RoomJoinRequested(id));
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

  Widget _buildBody(RoomsState state) {
    return switch (state) {
      RoomsInitial() || RoomsLoadInProgress() => const Center(
          child: CircularProgressIndicator(),
        ),
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
      RoomsLoaded(:final rooms, :final submitting) => Column(
          children: [
            if (submitting) const LinearProgressIndicator(),
            Expanded(
              child: rooms.isEmpty
                  ? const Center(
                      child: Text('No rooms yet. Create or join one.'),
                    )
                  : ListView.builder(
                      itemCount: rooms.length,
                      itemBuilder: (context, index) => ListTile(
                        title: Text(rooms[index].name),
                        onTap: () => context.go(
                          '/rooms/${rooms[index].id}'
                          '?name=${Uri.encodeComponent(rooms[index].name)}',
                        ),
                      ),
                    ),
            ),
          ],
        ),
    };
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

  final ValueChanged<int> onSubmit;

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
    final id = int.tryParse(_controller.text.trim());
    if (id == null) return;
    widget.onSubmit(id);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Join a room'),
      content: TextField(
        controller: _controller,
        keyboardType: TextInputType.number,
        autofocus: true,
        decoration: const InputDecoration(
          labelText: 'Room ID',
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
