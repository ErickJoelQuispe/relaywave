import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../../auth/presentation/auth_bloc.dart';
import '../../auth/presentation/auth_state.dart';
import '../../../core/theme/tokens.dart';
import '../data/message_cache.dart';
import '../domain/chat_repository.dart';
import '../domain/message.dart';
import 'chat_bloc.dart';
import 'chat_event.dart';
import 'chat_state.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.roomId, required this.roomName});

  final int roomId;
  final String roomName;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  @override
  Widget build(BuildContext context) {
    final chatRepository = context.read<ChatRepository>();
    return BlocProvider(
      create: (_) => ChatBloc(
        repository: chatRepository,
        cache: context.read<MessageCache>(),
        roomId: widget.roomId,
      )..add(const ChatConnectRequested()),
      child: _ChatView(roomId: widget.roomId, roomName: widget.roomName),
    );
  }
}

class _ChatView extends StatefulWidget {
  const _ChatView({required this.roomId, required this.roomName});

  final int roomId;
  final String roomName;

  @override
  State<_ChatView> createState() => _ChatViewState();
}

class _ChatViewState extends State<_ChatView> {
  final TextEditingController _inputController = TextEditingController();

  @override
  void dispose() {
    _inputController.dispose();
    super.dispose();
  }

  void _sendMessage() {
    final text = _inputController.text.trim();
    if (text.isEmpty) return;
    context.read<ChatBloc>().add(ChatMessageSendRequested(text));
    _inputController.clear();
  }

  @override
  Widget build(BuildContext context) {
    final myUserId = context.select<AuthBloc, int?>((bloc) {
      final s = bloc.state;
      return s is AuthAuthenticated ? s.user.id : null;
    });
    final state = context.watch<ChatBloc>().state;
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    final onlineCount = switch (state) {
      ChatActive(:final onlineUserIds) => onlineUserIds.length,
      _ => null,
    };

    return Scaffold(
      appBar: AppBar(
        leading: MediaQuery.sizeOf(context).width < AppBreakpoints.desktop
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                tooltip: 'Back',
                onPressed: () => context.go('/'),
              )
            : null,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(widget.roomName),
            if (onlineCount != null)
              Text(
                '$onlineCount online',
                style: textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                ),
              ),
          ],
        ),
      ),
      body: SafeArea(
        child: BlocBuilder<ChatBloc, ChatState>(
          builder: (context, state) => _buildBody(
            state,
            myUserId,
            colorScheme,
            textTheme,
          ),
        ),
      ),
    );
  }

  Widget _buildBody(
    ChatState state,
    int? myUserId,
    ColorScheme colorScheme,
    TextTheme textTheme,
  ) {
    return switch (state) {
      ChatConnecting() => const Center(child: CircularProgressIndicator()),
      ChatFailed(:final message) => Center(
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.lg),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(message, textAlign: TextAlign.center),
                const SizedBox(height: AppSpacing.lg),
                FilledButton(
                  onPressed: () => context
                      .read<ChatBloc>()
                      .add(const ChatReconnectRequested()),
                  child: const Text('Retry'),
                ),
              ],
            ),
          ),
        ),
      final ChatActive active => _buildActive(
          active,
          myUserId,
          colorScheme,
          textTheme,
        ),
    };
  }

  Widget _buildActive(
    ChatActive state,
    int? myUserId,
    ColorScheme colorScheme,
    TextTheme textTheme,
  ) {
    final messages = state.messages;
    return Column(
      children: [
        if (!state.isConnected) _buildReconnectBanner(colorScheme),
        Expanded(
          child: messages.isEmpty
              ? const Center(child: Text('No messages yet.'))
              : ListView.builder(
                  reverse: true,
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.lg,
                    vertical: AppSpacing.md,
                  ),
                  itemCount: messages.length,
                  itemBuilder: (context, index) {
                    final message = messages[messages.length - 1 - index];
                    return _MessageBubble(
                      message: message,
                      isMine: message.senderId == myUserId,
                    );
                  },
                ),
        ),
        if (state.typingUserIds.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.lg,
              vertical: AppSpacing.xs,
            ),
            child: Align(
              alignment: Alignment.centerLeft,
              child: Text(
                'Someone is typing...',
                style: textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                ),
              ),
            ),
          ),
        _buildInputBar(colorScheme),
      ],
    );
  }

  Widget _buildReconnectBanner(ColorScheme colorScheme) {
    return Container(
      width: double.infinity,
      color: colorScheme.errorContainer,
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.xs,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              'Connection lost. Reconnecting...',
              style: TextStyle(color: colorScheme.onErrorContainer),
            ),
          ),
          TextButton(
            style: TextButton.styleFrom(
              foregroundColor: colorScheme.onErrorContainer,
            ),
            onPressed: () =>
                context.read<ChatBloc>().add(const ChatReconnectRequested()),
            child: const Text('Retry'),
          ),
        ],
      ),
    );
  }

  Widget _buildInputBar(ColorScheme colorScheme) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.md,
        vertical: AppSpacing.sm,
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _inputController,
              decoration: const InputDecoration(hintText: 'Message'),
              textInputAction: TextInputAction.send,
              onChanged: (_) => context
                  .read<ChatBloc>()
                  .add(const ChatTypingSendRequested()),
              onSubmitted: (_) => _sendMessage(),
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          IconButton(
            icon: const Icon(Icons.send),
            tooltip: 'Send',
            onPressed: _sendMessage,
          ),
        ],
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({required this.message, required this.isMine});

  final Message message;
  final bool isMine;

  String _formatTime(DateTime time) {
    final hour = time.hour.toString().padLeft(2, '0');
    final minute = time.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    final bubbleColor = isMine
        ? colorScheme.primary
        : colorScheme.surfaceContainerHighest;
    final textColor = isMine ? colorScheme.onPrimary : colorScheme.onSurface;
    final timeColor = isMine
        ? colorScheme.onPrimary.withValues(alpha: 0.7)
        : colorScheme.onSurfaceVariant;

    return Align(
      alignment: isMine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.75,
        ),
        decoration: BoxDecoration(
          color: bubbleColor,
          borderRadius: BorderRadius.circular(AppRadius.md),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message.content, style: TextStyle(color: textColor)),
            const SizedBox(height: AppSpacing.xs),
            Text(
              _formatTime(message.createdAt),
              style: textTheme.labelSmall?.copyWith(color: timeColor),
            ),
          ],
        ),
      ),
    );
  }
}
