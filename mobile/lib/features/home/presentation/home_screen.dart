import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../auth/presentation/auth_bloc.dart';
import '../../auth/presentation/auth_event.dart';
import '../../auth/presentation/auth_state.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final authState = context.watch<AuthBloc>().state;
    final username = switch (authState) {
      AuthAuthenticated(:final user) => user.username,
      _ => '…',
    };

    return Scaffold(
      appBar: AppBar(
        title: const Text('Relaywave'),
      ),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text('Hello, $username'),
            const SizedBox(height: 16),
            OutlinedButton(
              onPressed: () =>
                  context.read<AuthBloc>().add(const AuthLogoutRequested()),
              child: const Text('Log out'),
            ),
          ],
        ),
      ),
    );
  }
}
