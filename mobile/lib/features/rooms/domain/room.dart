import 'package:equatable/equatable.dart';

final class Room extends Equatable {
  const Room({
    required this.id,
    required this.name,
    required this.createdAt,
    this.createdBy,
  });

  final int id;
  final String name;
  final int? createdBy;
  final DateTime createdAt;

  factory Room.fromJson(Map<String, dynamic> json) => Room(
        id: json['id'] as int,
        name: json['name'] as String,
        createdBy: json['created_by'] as int?,
        createdAt: DateTime.parse(json['created_at'] as String),
      );

  @override
  List<Object?> get props => [id, name, createdBy, createdAt];
}
