import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../../auth/presentation/auth_bloc.dart';
import '../../auth/presentation/auth_state.dart';
import '../../../core/theme/tokens.dart';
import '../../../core/widgets/shimmer_list_placeholder.dart';
import '../../rooms/data/room_cache.dart';
import '../../rooms/domain/room_repository.dart';
import '../../rooms/presentation/room_info_cubit.dart';
import '../../rooms/presentation/room_info_panel.dart';
import '../../rooms/presentation/room_info_state.dart';
import '../data/message_cache.dart';
import '../domain/chat_repository.dart';
import '../domain/message.dart';
import 'chat_bloc.dart';
import 'chat_event.dart';
import 'chat_state.dart';
import 'typing_indicator.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key, required this.roomId});

  final int roomId;

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
      child: BlocProvider(
        // F3-R1: the header title and the room-info panel share one source —
        // fresh detail, else the cached row, else the generic `Room #id`
        // placeholder. The chat route passes only the room id now.
        create: (_) => RoomInfoCubit(
          repository: context.read<RoomRepository>(),
          cache: context.read<RoomCache>(),
          roomId: widget.roomId,
        )..load(),
        child: _ChatView(roomId: widget.roomId),
      ),
    );
  }
}

class _ChatView extends StatefulWidget {
  const _ChatView({required this.roomId});

  final int roomId;

  @override
  State<_ChatView> createState() => _ChatViewState();
}

class _ChatViewState extends State<_ChatView> {
  final TextEditingController _inputController = TextEditingController();

  final Set<int> _seenMessageIds = {};
  bool _seenInitialized = false;
  bool _pressed = false;

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

  /// Current presence-delta count from the live socket, or null while the
  /// connection is not active. Read-only (the caller watches ChatBloc for
  /// rebuilds); safe to call outside build, e.g. when opening the panel.
  int? _onlineCountOf(BuildContext context) {
    final state = context.read<ChatBloc>().state;
    return switch (state) {
      ChatActive(:final onlineUserIds) => onlineUserIds.length,
      _ => null,
    };
  }

  Future<void> _openRoomInfo() async {
    // F3-R1: every open fetches fresh detail from the server.
    await context.read<RoomInfoCubit>().refresh();
    if (!mounted) return;
    await showModalBottomSheet<void>(
      context: context,
      builder: (sheetContext) => BlocProvider.value(
        // The sheet is pushed onto the root navigator, above this cubit's
        // provider — re-expose it so the panel can read and refresh it.
        value: context.read<RoomInfoCubit>(),
        child: RoomInfoPanel(
          roomId: widget.roomId,
          onlineCount: _onlineCountOf(context),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final myUserId = context.select<AuthBloc, int?>((bloc) {
      final s = bloc.state;
      return s is AuthAuthenticated ? s.user.id : null;
    });
    // The ChatBloc watch keeps the header count live as presence deltas
    // arrive; the read-only helper is safe to call outside build (panel).
    final onlineCount = switch (context.watch<ChatBloc>().state) {
      ChatActive(:final onlineUserIds) => onlineUserIds.length,
      _ => null,
    };
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;
    final infoState = context.watch<RoomInfoCubit>().state;
    // F3-R1: authoritative detail, else cache, else the generic placeholder
    // — never a name fabricated from the URL (the ?name= hack is gone).
    final roomTitle = switch (infoState) {
      RoomInfoLoaded(:final room) => room.displayTitle,
      _ => 'Room #${widget.roomId}',
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
            Text(roomTitle, overflow: TextOverflow.ellipsis),
            if (onlineCount != null)
              Text(
                // F3-R2: the presence-delta count is inherently approximate —
                // this client may undercount (late join, backgrounding,
                // cross-replica deltas) — so every surface carrying it must
                // label it as an estimate.
                '~$onlineCount online (estimate)',
                style: textTheme.bodySmall?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                ),
              ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.info_outline),
            tooltip: 'Room info',
            onPressed: _openRoomInfo,
          ),
        ],
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
      ChatConnecting() => const ShimmerListPlaceholder(itemCount: 6),
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

    // Seed the "seen" set on the very first render so history that is already
    // present when the screen opens does not animate in. Only messages that
    // arrive later (after the screen is showing) are treated as new.
    if (!_seenInitialized) {
      _seenMessageIds.addAll(messages.map((m) => m.id));
      _seenInitialized = true;
    }

    return Column(
      children: [
        AnimatedSize(
          duration: const Duration(milliseconds: 280),
          curve: Curves.easeOut,
          child: state.isConnected
              ? const SizedBox.shrink()
              : _buildReconnectBanner(colorScheme),
        ),
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
                    final bubble = _MessageBubble(
                      message: message,
                      isMine: message.senderId == myUserId,
                    );
                    // A message already in the seen set is a re-render of
                    // previously shown content and must not animate in again.
                    final isNew = _seenMessageIds.add(message.id);
                    if (!isNew) return bubble;
                    return bubble
                        .animate()
                        .fadeIn(duration: 150.ms, curve: Curves.easeOut)
                        .slideY(
                          begin: 0.08,
                          end: 0,
                          duration: 150.ms,
                          curve: Curves.easeOut,
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
              child: Row(
                children: [
                  const TypingIndicator(),
                  const SizedBox(width: AppSpacing.sm),
                  Text(
                    'Someone is typing...',
                    style: textTheme.bodySmall?.copyWith(
                      color: colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
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
          Listener(
            onPointerDown: (_) => setState(() => _pressed = true),
            onPointerUp: (_) => setState(() => _pressed = false),
            onPointerCancel: (_) => setState(() => _pressed = false),
            child: IconButton(
              icon: const Icon(Icons.send),
              tooltip: 'Send',
              onPressed: _sendMessage,
            ).animate(
              target: _pressed ? 1 : 0,
            ).scale(
              begin: const Offset(1, 1),
              end: const Offset(0.92, 0.92),
              duration: 120.ms,
              curve: Curves.easeOut,
            ),
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
