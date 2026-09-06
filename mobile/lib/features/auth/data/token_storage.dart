import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract interface class TokenStorage {
  Future<String?> readAccessToken();

  Future<String?> readRefreshToken();

  Future<void> writeTokens({required String access, required String refresh});

  Future<void> clear();
}

final class SecureTokenStorage implements TokenStorage {
  SecureTokenStorage({FlutterSecureStorage? storage})
      : _storage = storage ?? FlutterSecureStorage();

  final FlutterSecureStorage _storage;

  // In-memory cache: on Linux, flutter_secure_storage is backed by the
  // OS-wide libsecret/gnome-keyring, scoped to the D-Bus session rather
  // than per-process $HOME/$XDG dirs. Two app instances under the same
  // login session share the same keyring entries, so re-reading from
  // disk on every request lets one instance's login silently overwrite
  // the token the other instance is using. Caching in memory after the
  // first load/write means each running process keeps using its own
  // session once it has one, regardless of what another instance later
  // writes to the shared backing store.
  String? _cachedAccess;
  String? _cachedRefresh;
  bool _cacheLoaded = false;

  static const String _accessKey = 'access_token';
  static const String _refreshKey = 'refresh_token';

  Future<void> _ensureCacheLoaded() async {
    if (_cacheLoaded) return;
    _cachedAccess = await _storage.read(key: _accessKey);
    _cachedRefresh = await _storage.read(key: _refreshKey);
    _cacheLoaded = true;
  }

  @override
  Future<String?> readAccessToken() async {
    await _ensureCacheLoaded();
    return _cachedAccess;
  }

  @override
  Future<String?> readRefreshToken() async {
    await _ensureCacheLoaded();
    return _cachedRefresh;
  }

  @override
  Future<void> writeTokens({
    required String access,
    required String refresh,
  }) async {
    _cachedAccess = access;
    _cachedRefresh = refresh;
    _cacheLoaded = true;
    await _storage.write(key: _accessKey, value: access);
    await _storage.write(key: _refreshKey, value: refresh);
  }

  @override
  Future<void> clear() async {
    _cachedAccess = null;
    _cachedRefresh = null;
    _cacheLoaded = true;
    await _storage.delete(key: _accessKey);
    await _storage.delete(key: _refreshKey);
  }
}
