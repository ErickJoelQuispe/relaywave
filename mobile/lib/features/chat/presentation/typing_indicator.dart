import 'package:flutter/material.dart';
import 'package:flutter_animate/flutter_animate.dart';

import '../../../core/theme/tokens.dart';

/// Three small dots that pulse in sequence to signal that someone is typing.
class TypingIndicator extends StatelessWidget {
  const TypingIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.onSurfaceVariant;

    Widget dot(int index) {
      return Container(
        width: 8,
        height: 8,
        decoration: BoxDecoration(color: color, shape: BoxShape.circle),
      ).animate(
        delay: (150 * index).ms,
        onPlay: (controller) => controller.repeat(reverse: true),
      ).scale(
        duration: 400.ms,
        begin: const Offset(0.6, 0.6),
        end: const Offset(1, 1),
      );
    }

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        for (var i = 0; i < 3; i++) ...[
          if (i > 0) const SizedBox(width: AppSpacing.xs),
          dot(i),
        ],
      ],
    );
  }
}
