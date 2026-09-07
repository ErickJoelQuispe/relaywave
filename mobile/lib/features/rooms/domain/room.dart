import 'package:equatable/equatable.dart';

final class Room extends Equatable {
  const Room({
    required this.id,
    required this.name,
    required this.createdAt,
    this.createdBy,
    this.kind = 'group',
    this.capacity,
    this.peerUsername,
    this.memberCount,
  });

  final int id;
  final String name;
  final int? createdBy;
  final DateTime createdAt;

  /// Server-set discriminator: 'group' | 'dm' (F1-R7). Defaults to 'group'
  /// so cached rows written before the field existed still render as groups.
  final String kind;

  /// Display-only metadata from room detail (F3-R3); null for DM rooms.
  final int? capacity;

  /// The other user's username, present only on DM rows (F1-R7). Clients
  /// must title DM rooms from this and never show the internal `dm-*` name.
  final String? peerUsername;

  /// Authoritative membership count from room detail (list rows omit it).
  final int? memberCount;

  /// Title source: the peer's username for DMs, the canonical slug otherwise.
  String get displayTitle => peerUsername ?? name;

  factory Room.fromJson(Map<String, dynamic> json) => Room(
        id: json['id'] as int,
        name: json['name'] as String,
        createdBy: json['created_by'] as int?,
        createdAt: DateTime.parse(json['created_at'] as String),
        kind: json['kind'] as String? ?? 'group',
        capacity: json['capacity'] as int?,
        peerUsername: json['peer_username'] as String?,
        memberCount: json['member_count'] as int?,
      );

  @override
  List<Object?> get props => [
        id,
        name,
        createdBy,
        createdAt,
        kind,
        capacity,
        peerUsername,
        memberCount,
      ];
}
