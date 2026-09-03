import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../core/theme/tokens.dart';
import '../features/rooms/presentation/rooms_pane.dart';

class ResponsiveShell extends StatelessWidget {
  const ResponsiveShell({
    super.key,
    required this.state,
    required this.child,
  });

  final GoRouterState state;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < AppBreakpoints.desktop) {
          return child;
        }

        return Scaffold(
          body: Row(
            children: [
              const SizedBox(width: 320, child: RoomsPane()),
              const VerticalDivider(width: 1),
              Expanded(
                child: state.uri.path == '/'
                    ? const _SelectRoomPlaceholder()
                    : child,
              ),
            ],
          ),
        );
      },
    );
  }
}

class _SelectRoomPlaceholder extends StatelessWidget {
  const _SelectRoomPlaceholder();

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            Icons.forum_outlined,
            size: 48,
            color: colorScheme.onSurfaceVariant,
          ),
          const SizedBox(height: AppSpacing.lg),
          Text(
            'Select a room to start chatting',
            style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                  color: colorScheme.onSurfaceVariant,
                ),
          ),
        ],
      ),
    );
  }
}
