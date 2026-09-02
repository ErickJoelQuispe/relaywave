import 'package:flutter/material.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Relaywave'),
      ),
      body: const Center(
        child: Text('Chat rooms will appear here in a later slice.'),
      ),
    );
  }
}
