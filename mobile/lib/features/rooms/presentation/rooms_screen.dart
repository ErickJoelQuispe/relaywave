import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../auth/presentation/auth_bloc.dart';
import '../../auth/presentation/auth_event.dart';
import 'rooms_bloc.dart';
import 'rooms_event.dart';
import 'rooms_state.dart';

class RoomsScreen extends StatefulWidget {
  const RoomsScreen({super.key});

  @override
  State<RoomsScreen> createState() => _RoomsScreenState();
}

class _RoomsScreenState extends State<RoomsScreen> {
  @override
  void initState() {
    super.initState();
    context.read<RoomBloc>().add(const RoomsLoadRequested());
  }

  Future<void> _showJoinRoomDialog() async {
    final controller = TextEditingController();
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Join a room'),
          content: TextField(
            controller: controller,
            keyboardType: TextInputType.number,
            autofocus: true,
            decoration: const InputDecoration(
              labelText: 'Room ID',
              border: OutlineInputBorder(),
            ),
            onSubmitted: (_) => _submitJoin(dialogContext, controller),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => _submitJoin(dialogContext, controller),
              child: const Text('Join'),
            ),
          ],
        );
      },
    );
    controller.dispose();
  }

  void _submitJoin(
    BuildContext dialogContext,
    TextEditingController controller,
  ) {
    final id = int.tryParse(controller.text.trim());
    if (id == null) return;
    context.read<RoomBloc>().add(RoomJoinRequested(id));
    Navigator.of(dialogContext).pop();
  }

  Future<void> _showCreateRoomDialog() async {
    final controller = TextEditingController();
    await showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('Create room'),
          content: TextField(
            controller: controller,
            autofocus: true,
            decoration: const InputDecoration(
              labelText: 'Room name',
              border: OutlineInputBorder(),
            ),
            onSubmitted: (_) => _submitCreate(dialogContext, controller),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => _submitCreate(dialogContext, controller),
              child: const Text('Create'),
            ),
          ],
        );
      },
    );
    controller.dispose();
  }

  void _submitCreate(
    BuildContext dialogContext,
    TextEditingController controller,
  ) {
    final name = controller.text.trim();
    if (name.isEmpty) return;
    context.read<RoomBloc>().add(RoomCreateRequested(name));
    Navigator.of(dialogContext).pop();
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
                      itemBuilder: (context, index) =>
                          ListTile(title: Text(rooms[index].name)),
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
