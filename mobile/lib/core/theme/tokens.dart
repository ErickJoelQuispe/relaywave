import 'package:flutter/material.dart';

abstract final class AppColors {
  // Brand (light) — indigo
  static const primary = Color(0xFF6366F1);
  static const onPrimary = Color(0xFFFFFFFF);
  static const primaryContainer = Color(0xFFE0E7FF);
  static const onPrimaryContainer = Color(0xFF3730A3);

  // Semantic — online is presence only
  static const online = Color(0xFF059669);
  static const onlineDark = Color(0xFF34D399);

  // Neutral ramp (light) — slate
  static const surface = Color(0xFFFFFFFF);
  static const onSurface = Color(0xFF0F172A);
  static const surfaceMuted = Color(0xFFF1F5F9);
  static const onSurfaceVariant = Color(0xFF64748B);
  static const outline = Color(0xFFE2E8F0);
  static const outlineVariant = Color(0xFFCBD5E1);

  // Error (light)
  static const error = Color(0xFFDC2626);
  static const errorContainer = Color(0xFFFEE2E2);
  static const onErrorContainer = Color(0xFF991B1B);

  // Dark — brand
  static const primaryDark = Color(0xFF818CF8);
  static const onPrimaryDark = Color(0xFF1E1B4B);
  static const primaryContainerDark = Color(0xFF3730A3);
  static const onPrimaryContainerDark = Color(0xFFE0E7FF);

  // Dark — neutral
  static const surfaceDark = Color(0xFF0F172A);
  static const onSurfaceDark = Color(0xFFE2E8F0);
  static const surfaceMutedDark = Color(0xFF1E293B);
  static const onSurfaceVariantDark = Color(0xFF94A3B8);
  static const outlineDark = Color(0xFF334155);

  // Dark — error
  static const errorDark = Color(0xFFF87171);
  static const errorContainerDark = Color(0xFF7F1D1D);
  static const onErrorContainerDark = Color(0xFFFEE2E2);
}

abstract final class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
  static const double xxxl = 48;
}

abstract final class AppRadius {
  static const double sm = 8;   // inputs, buttons
  static const double md = 12;  // cards
  static const double lg = 16;  // modals / sheets
  static const double pill = 999;
}

abstract final class AppBreakpoints {
  static const double desktop = 840; // Material "expanded" breakpoint
}
