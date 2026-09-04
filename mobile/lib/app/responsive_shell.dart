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
        final isWide = constraints.maxWidth >= AppBreakpoints.desktop;
        final detail = isWide && state.uri.path == '/'
            ? const _SelectRoomPlaceholder()
            : child;

        // `child` must keep the exact same ancestor depth/shape on both
        // narrow and wide layouts. Resizing across [AppBreakpoints.desktop]
        // (e.g. a tiling window manager reflowing the window) used to swap
        // `child` between "direct" and "3 levels deep under Scaffold/Row/
        // Expanded" in the same frame, which corrupted the element tree
        // (disposed TextEditingController, `_dependents.isEmpty` assertion).
        // Keeping Scaffold > Row > Expanded constant and only toggling the
        // leading rooms pane avoids reparenting `child` altogether.
        return Scaffold(
          body: Row(
            children: [
              if (isWide) ...[
                const SizedBox(width: 320, child: RoomsPane()),
                const VerticalDivider(width: 1),
              ],
              Expanded(
                child: KeyedSubtree(
                  key: const ValueKey('responsive-shell-detail'),
                  child: detail,
                ),
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
