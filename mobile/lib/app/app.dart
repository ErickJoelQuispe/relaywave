import 'package:flutter/material.dart';

import 'router.dart';
import 'theme.dart';

class RelaywaveApp extends StatelessWidget {
  const RelaywaveApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Relaywave',
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: router,
    );
  }
}
