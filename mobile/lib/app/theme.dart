import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../core/theme/tokens.dart';

abstract final class AppTheme {
  static ThemeData get light {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.primary,
        brightness: Brightness.light,
      ).copyWith(
        primary: AppColors.primary,
        onPrimary: AppColors.onPrimary,
        primaryContainer: AppColors.primaryContainer,
        onPrimaryContainer: AppColors.onPrimaryContainer,
        surface: AppColors.surface,
        onSurface: AppColors.onSurface,
        surfaceContainerHighest: AppColors.surfaceMuted,
        onSurfaceVariant: AppColors.onSurfaceVariant,
        outline: AppColors.outline,
        outlineVariant: AppColors.outlineVariant,
        error: AppColors.error,
        errorContainer: AppColors.errorContainer,
        onErrorContainer: AppColors.onErrorContainer,
      ),
    );

    final textTheme = _buildTextTheme(base.textTheme);

    return base.copyWith(
      textTheme: textTheme,
      inputDecorationTheme: _inputDecorationTheme(base.colorScheme),
      filledButtonTheme: _filledButtonTheme(base.colorScheme),
      textButtonTheme: _textButtonTheme(base.colorScheme),
      appBarTheme: _appBarTheme(base.colorScheme, textTheme),
      snackBarTheme: const SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(AppRadius.md)),
        ),
      ),
      listTileTheme: ListTileThemeData(
        iconColor: base.colorScheme.onSurfaceVariant,
      ),
    );
  }

  static ThemeData get dark {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.primary,
        brightness: Brightness.dark,
      ).copyWith(
        primary: AppColors.primaryDark,
        onPrimary: AppColors.onPrimaryDark,
        primaryContainer: AppColors.primaryContainerDark,
        onPrimaryContainer: AppColors.onPrimaryContainerDark,
        surface: AppColors.surfaceDark,
        onSurface: AppColors.onSurfaceDark,
        surfaceContainerHighest: AppColors.surfaceMutedDark,
        onSurfaceVariant: AppColors.onSurfaceVariantDark,
        outline: AppColors.outlineDark,
        error: AppColors.errorDark,
        errorContainer: AppColors.errorContainerDark,
        onErrorContainer: AppColors.onErrorContainerDark,
      ),
    );

    final textTheme = _buildTextTheme(base.textTheme);

    return base.copyWith(
      textTheme: textTheme,
      inputDecorationTheme: _inputDecorationTheme(base.colorScheme),
      filledButtonTheme: _filledButtonTheme(base.colorScheme),
      textButtonTheme: _textButtonTheme(base.colorScheme),
      appBarTheme: _appBarTheme(base.colorScheme, textTheme),
      snackBarTheme: const SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(AppRadius.md)),
        ),
      ),
      listTileTheme: ListTileThemeData(
        iconColor: base.colorScheme.onSurfaceVariant,
      ),
    );
  }

  static TextTheme _buildTextTheme(TextTheme base) {
    return GoogleFonts.interTextTheme(base).copyWith(
      headlineMedium: base.headlineMedium?.copyWith(
        fontWeight: FontWeight.w600,
        letterSpacing: -0.5,
      ),
    );
  }

  static InputDecorationTheme _inputDecorationTheme(ColorScheme scheme) {
    return InputDecorationTheme(
      filled: true,
      fillColor: scheme.surfaceContainerHighest,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        borderSide: BorderSide(color: scheme.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        borderSide: BorderSide(color: scheme.outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        borderSide: BorderSide(color: scheme.primary, width: 2),
      ),
      contentPadding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.lg,
        vertical: AppSpacing.md,
      ),
    );
  }

  static FilledButtonThemeData _filledButtonTheme(ColorScheme scheme) {
    return FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: scheme.primary,
        foregroundColor: scheme.onPrimary,
        minimumSize: const Size.fromHeight(48),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppRadius.sm),
        ),
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    );
  }

  static TextButtonThemeData _textButtonTheme(ColorScheme scheme) {
    return TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: scheme.primary,
        textStyle: const TextStyle(fontWeight: FontWeight.w600),
      ),
    );
  }

  static AppBarTheme _appBarTheme(ColorScheme scheme, TextTheme textTheme) {
    return AppBarTheme(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: textTheme.titleLarge?.copyWith(
        color: scheme.onSurface,
        fontWeight: FontWeight.w600,
      ),
      iconTheme: IconThemeData(color: scheme.onSurface),
    );
  }
}
