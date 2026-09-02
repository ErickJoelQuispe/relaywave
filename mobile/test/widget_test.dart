import 'package:flutter_test/flutter_test.dart';

import 'package:relaywave_mobile/app/app.dart';

void main() {
  testWidgets('Relaywave app renders the home screen', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const RelaywaveApp());
    await tester.pumpAndSettle();

    expect(find.text('Relaywave'), findsWidgets);
  });
}
