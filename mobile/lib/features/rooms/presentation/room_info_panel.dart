import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../core/theme/tokens.dart';
import 'room_info_cubit.dart';
import 'room_info_state.dart';

/// Room-info bottom sheet: authoritative title, approximate live count, and
/// display-only capacity (F3-R2). Opened from the chat header; the caller
/// calls `RoomInfoCubit.refresh()` first so every open fetches fresh detail.
///
/// `onlineCount` comes from the caller's `ChatBloc` state (the WS presence
/// delta set) — the cubit never touches the socket. The count is inherently
/// approximate (this client may undercount), so it is always labeled as an
/// estimate, never presented as authoritative.
class RoomInfoPanel extends StatelessWidget {
  const RoomInfoPanel({
    super.key,
    required this.roomId,
    required this.onlineCount,
  });

  final int roomId;
  final int? onlineCount;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    final colorScheme = Theme.of(context).colorScheme;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: BlocBuilder<RoomInfoCubit, RoomInfoState>(
          builder: (context, state) {
            final room = switch (state) {
              RoomInfoLoaded(:final room) => room,
              _ => null,
            };
            final title = room?.displayTitle ?? 'Room #$roomId';

            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(title, style: textTheme.headlineSmall),
                    ),
                    IconButton(
                      icon: const Icon(Icons.refresh),
                      tooltip: 'Refresh room info',
                      onPressed: () =>
                          context.read<RoomInfoCubit>().refresh(),
                    ),
                    IconButton(
                      icon: const Icon(Icons.close),
                      tooltip: 'Close',
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                  ],
                ),
                if (room != null && room.kind != 'dm')
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: Text(
                      room.name,
                      style: textTheme.bodySmall?.copyWith(
                        color: colorScheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                const SizedBox(height: AppSpacing.lg),
                if (onlineCount != null)
                  _InfoRow(
                    icon: Icons.person_outline,
                    label: '~$onlineCount connected — estimate',
                  ),
                if (room?.capacity != null)
                  _InfoRow(
                    icon: Icons.groups_outlined,
                    label: 'Capacity: ${room!.capacity}',
                  ),
                const SizedBox(height: AppSpacing.xs),
                Text(
                  'Room #$roomId',
                  style: textTheme.bodySmall?.copyWith(
                    color: colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppSpacing.xs),
      child: Row(
        children: [
          Icon(icon, size: 18),
          const SizedBox(width: AppSpacing.sm),
          Text(label),
        ],
      ),
    );
  }
}
