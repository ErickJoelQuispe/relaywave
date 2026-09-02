abstract final class AppConfig {
  // Defaults to local desktop/web dev against the backend on 127.0.0.1:8000.
  // The Android emulator maps the host's localhost to 10.0.2.2, so it must
  // override this with --dart-define=API_BASE_URL=http://10.0.2.2:8000.
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );
}
