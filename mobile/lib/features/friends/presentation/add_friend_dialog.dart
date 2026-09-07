import 'package:flutter/material.dart';

class AddFriendDialog extends StatefulWidget {
  const AddFriendDialog({super.key, required this.onSubmit});

  final ValueChanged<String> onSubmit;

  @override
  State<AddFriendDialog> createState() => _AddFriendDialogState();
}

class _AddFriendDialogState extends State<AddFriendDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final username = _controller.text.trim();
    if (username.isEmpty) return;
    widget.onSubmit(username);
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Add a friend'),
      content: TextField(
        controller: _controller,
        autofocus: true,
        decoration: const InputDecoration(
          labelText: 'Username',
          border: OutlineInputBorder(),
        ),
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton(
          onPressed: _submit,
          child: const Text('Send request'),
        ),
      ],
    );
  }
}
