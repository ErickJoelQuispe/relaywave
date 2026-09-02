import 'package:dio/dio.dart';

final class ApiException implements Exception {
  const ApiException(this.message);

  final String message;

  @override
  String toString() => message;
}

String dioErrorMessage(DioException error) {
  final data = error.response?.data;
  if (data is Map) {
    final detail = data['detail'];
    if (detail is String) {
      return detail;
    }
    if (detail is List && detail.isNotEmpty && detail.first is Map) {
      final first = detail.first as Map;
      if (first['msg'] is String) {
        return first['msg'] as String;
      }
    }
  }
  if (error.response == null) {
    return 'Unable to reach the server. Please try again.';
  }
  return 'Something went wrong. Please try again.';
}
