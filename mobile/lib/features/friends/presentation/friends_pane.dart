import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../../../core/theme/tokens.dart';
import '../domain/friend.dart';
import 'add_friend_dialog.dart';
import 'friends_bloc.dart';
import 'friends_event.dart';
import 'friends_state.dart';

class FriendsPane extends StatefulWidget {
  const FriendsPane({super.key});

  @override
  State<FriendsPane> createState() => _FriendsPaneState();
}

class _FriendsPaneState extends State<FriendsPane> {
  @override
  void initState() {
    super.initState();
    context.read<FriendsBloc>().add(const FriendsLoadRequested());
  }

  Future<void> _showAddFriendDialog() async {
    await showDialog<void>(
      context: context,
      builder: (dialogContext) => AddFriendDialog(
        onSubmit: (username) {
          context.read<FriendsBloc>().add(FriendAddRequested(username));
          Navigator.of(dialogContext).pop();
        },
      ),
    );
  }

  Widget _buildBody(FriendsState state) {
    return switch (state) {
      FriendsInitial() || FriendsLoadInProgress() =>
        const Center(child: CircularProgressIndicator()),
      FriendsLoadFailure(:final message) => Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(message, textAlign: TextAlign.center),
              const SizedBox(height: 16),
              OutlinedButton(
                onPressed: () =>
                    context.read<FriendsBloc>().add(const FriendsLoadRequested()),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      FriendsLoaded(
        :final friends,
        :final incoming,
        :final outgoing,
        :final blocked,
        :final submitting,
      ) =>
        _buildLoaded(friends, incoming, outgoing, blocked, submitting),
    };
  }

  Widget _buildLoaded(
    List<Friend> friends,
    List<FriendRequest> incoming,
    List<FriendRequest> outgoing,
    List<Friend> blocked,
    bool submitting,
  ) {
    final isEmpty =
        friends.isEmpty && incoming.isEmpty && outgoing.isEmpty && blocked.isEmpty;

    if (isEmpty) {
      return const Center(
        child: Text('No friends yet. Add someone by username.'),
      );
    }

    final children = <Widget>[
      if (submitting) const LinearProgressIndicator(),
      if (friends.isNotEmpty) ...[
        const _SectionHeader('Friends'),
        for (final friend in friends)
          _FriendTile(
            friend: friend,
            onRemove: () =>
                context.read<FriendsBloc>().add(FriendRemoveRequested(friend.id)),
          ),
      ],
      if (incoming.isNotEmpty) ...[
        const _SectionHeader('Incoming requests'),
        for (final request in incoming)
          _IncomingRequestTile(
            request: request,
            onAccept: () => context
                .read<FriendsBloc>()
                .add(FriendAcceptRequested(request.id)),
            onDecline: () => context
                .read<FriendsBloc>()
                .add(FriendDeclineRequested(request.id)),
          ),
      ],
      if (outgoing.isNotEmpty) ...[
        const _SectionHeader('Outgoing requests'),
        for (final request in outgoing)
          ListTile(
            title: Text(request.username),
            subtitle: const Text('Pending'),
          ),
      ],
      if (blocked.isNotEmpty) ...[
        const _SectionHeader('Blocked'),
        for (final user in blocked)
          ListTile(
            title: Text(user.username),
            trailing: IconButton(
              icon: const Icon(Icons.lock_open_outlined),
              tooltip: 'Unblock',
              onPressed: () => context
                  .read<FriendsBloc>()
                  .add(FriendUnblockRequested(user.id)),
            ),
          ),
      ],
    ];

    return ListView(children: children);
  }

  @override
  Widget build(BuildContext context) {
    return BlocListener<FriendsBloc, FriendsState>(
      listener: (context, state) {
        final error = switch (state) {
          FriendsLoaded(:final error) => error,
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
          leading: MediaQuery.sizeOf(context).width < AppBreakpoints.desktop
              ? IconButton(
                  icon: const Icon(Icons.arrow_back),
                  tooltip: 'Back',
                  onPressed: () => context.go('/'),
                )
              : null,
          title: const Text('Friends'),
          actions: [
            IconButton(
              icon: const Icon(Icons.person_add_alt),
              tooltip: 'Add a friend',
              onPressed: _showAddFriendDialog,
            ),
          ],
        ),
        body: BlocBuilder<FriendsBloc, FriendsState>(
          builder: (context, state) => _buildBody(state),
        ),
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.lg,
        AppSpacing.lg,
        AppSpacing.lg,
        AppSpacing.xs,
      ),
      child: Text(
        title,
        style: textTheme.labelLarge?.copyWith(
          color: colorScheme.primary,
        ),
      ),
    );
  }
}

class _FriendTile extends StatelessWidget {
  const _FriendTile({required this.friend, required this.onRemove});

  final Friend friend;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final roomId = friend.roomId;
    return ListTile(
      title: Text(friend.username),
      subtitle: const Text('Direct message'),
      // A DM room always exists for a friendship; opening it reuses the
      // whole chat flow (title resolves to the peer username server-side).
      onTap: roomId == null
          ? null
          : () => context.go('/rooms/$roomId'),
      trailing: IconButton(
        icon: const Icon(Icons.person_remove_outlined),
        tooltip: 'Remove friend',
        onPressed: onRemove,
      ),
    );
  }
}

class _IncomingRequestTile extends StatelessWidget {
  const _IncomingRequestTile({
    required this.request,
    required this.onAccept,
    required this.onDecline,
  });

  final FriendRequest request;
  final VoidCallback onAccept;
  final VoidCallback onDecline;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(request.username),
      subtitle: const Text('Wants to chat'),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          IconButton(
            icon: const Icon(Icons.check),
            tooltip: 'Accept',
            onPressed: onAccept,
          ),
          IconButton(
            icon: const Icon(Icons.close),
            tooltip: 'Decline',
            onPressed: onDecline,
          ),
        ],
      ),
    );
  }
}
