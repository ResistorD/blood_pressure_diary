// GENERATED CODE - DO NOT MODIFY BY HAND

part of 'blood_pressure_model.dart';

// **************************************************************************
// IsarCollectionGenerator
// **************************************************************************

// coverage:ignore-file
// ignore_for_file: duplicate_ignore, non_constant_identifier_names, constant_identifier_names, invalid_use_of_protected_member, unnecessary_cast, prefer_const_constructors, lines_longer_than_80_chars, require_trailing_commas, inference_failure_on_function_invocation, unnecessary_parenthesis, unnecessary_raw_strings, unnecessary_null_checks, join_return_with_assignment, prefer_final_locals, avoid_js_rounded_ints, avoid_positional_boolean_parameters, always_specify_types

extension GetBloodPressureRecordCollection on Isar {
  IsarCollection<BloodPressureRecord> get bloodPressureRecords =>
      this.collection();
}

const BloodPressureRecordSchema = CollectionSchema(
  name: r'BloodPressureRecord',
  id: -3447328812780924616,
  properties: {
    r'dateTime': PropertySchema(
      id: 0,
      name: r'dateTime',
      type: IsarType.dateTime,
    ),
    r'diastolic': PropertySchema(
      id: 1,
      name: r'diastolic',
      type: IsarType.long,
    ),
    r'emotion': PropertySchema(
      id: 2,
      name: r'emotion',
      type: IsarType.string,
    ),
    r'note': PropertySchema(
      id: 3,
      name: r'note',
      type: IsarType.string,
    ),
    r'pulse': PropertySchema(
      id: 4,
      name: r'pulse',
      type: IsarType.long,
    ),
    r'systolic': PropertySchema(
      id: 5,
      name: r'systolic',
      type: IsarType.long,
    ),
    r'tags': PropertySchema(
      id: 6,
      name: r'tags',
      type: IsarType.stringList,
    )
  },
  estimateSize: _bloodPressureRecordEstimateSize,
  serialize: _bloodPressureRecordSerialize,
  deserialize: _bloodPressureRecordDeserialize,
  deserializeProp: _bloodPressureRecordDeserializeProp,
  idName: r'id',
  indexes: {
    r'dateTime': IndexSchema(
      id: -138851979697481250,
      name: r'dateTime',
      unique: false,
      replace: false,
      properties: [
        IndexPropertySchema(
          name: r'dateTime',
          type: IndexType.value,
          caseSensitive: false,
        )
      ],
    )
  },
  links: {},
  embeddedSchemas: {},
  getId: _bloodPressureRecordGetId,
  getLinks: _bloodPressureRecordGetLinks,
  attach: _bloodPressureRecordAttach,
  version: '3.1.0+1',
);

int _bloodPressureRecordEstimateSize(
  BloodPressureRecord object,
  List<int> offsets,
  Map<Type, List<int>> allOffsets,
) {
  var bytesCount = offsets.last;
  {
    final value = object.emotion;
    if (value != null) {
      bytesCount += 3 + value.length * 3;
    }
  }
  {
    final value = object.note;
    if (value != null) {
      bytesCount += 3 + value.length * 3;
    }
  }
  bytesCount += 3 + object.tags.length * 3;
  {
    for (var i = 0; i < object.tags.length; i++) {
      final value = object.tags[i];
      bytesCount += value.length * 3;
    }
  }
  return bytesCount;
}

void _bloodPressureRecordSerialize(
  BloodPressureRecord object,
  IsarWriter writer,
  List<int> offsets,
  Map<Type, List<int>> allOffsets,
) {
  writer.writeDateTime(offsets[0], object.dateTime);
  writer.writeLong(offsets[1], object.diastolic);
  writer.writeString(offsets[2], object.emotion);
  writer.writeString(offsets[3], object.note);
  writer.writeLong(offsets[4], object.pulse);
  writer.writeLong(offsets[5], object.systolic);
  writer.writeStringList(offsets[6], object.tags);
}

BloodPressureRecord _bloodPressureRecordDeserialize(
  Id id,
  IsarReader reader,
  List<int> offsets,
  Map<Type, List<int>> allOffsets,
) {
  final object = BloodPressureRecord();
  object.dateTime = reader.readDateTime(offsets[0]);
  object.diastolic = reader.readLong(offsets[1]);
  object.emotion = reader.readStringOrNull(offsets[2]);
  object.id = id;
  object.note = reader.readStringOrNull(offsets[3]);
  object.pulse = reader.readLong(offsets[4]);
  object.systolic = reader.readLong(offsets[5]);
  object.tags = reader.readStringList(offsets[6]) ?? [];
  return object;
}

P _bloodPressureRecordDeserializeProp<P>(
  IsarReader reader,
  int propertyId,
  int offset,
  Map<Type, List<int>> allOffsets,
) {
  switch (propertyId) {
    case 0:
      return (reader.readDateTime(offset)) as P;
    case 1:
      return (reader.readLong(offset)) as P;
    case 2:
      return (reader.readStringOrNull(offset)) as P;
    case 3:
      return (reader.readStringOrNull(offset)) as P;
    case 4:
      return (reader.readLong(offset)) as P;
    case 5:
      return (reader.readLong(offset)) as P;
    case 6:
      return (reader.readStringList(offset) ?? []) as P;
    default:
      throw IsarError('Unknown property with id $propertyId');
  }
}

Id _bloodPressureRecordGetId(BloodPressureRecord object) {
  return object.id;
}

List<IsarLinkBase<dynamic>> _bloodPressureRecordGetLinks(
    BloodPressureRecord object) {
  return [];
}

void _bloodPressureRecordAttach(
    IsarCollection<dynamic> col, Id id, BloodPressureRecord object) {
  object.id = id;
}

extension BloodPressureRecordQueryWhereSort
    on QueryBuilder<BloodPressureRecord, BloodPressureRecord, QWhere> {
  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhere> anyId() {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(const IdWhereClause.any());
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhere>
      anyDateTime() {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(
        const IndexWhereClause.any(indexName: r'dateTime'),
      );
    });
  }
}

extension BloodPressureRecordQueryWhere
    on QueryBuilder<BloodPressureRecord, BloodPressureRecord, QWhereClause> {
  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      idEqualTo(Id id) {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(IdWhereClause.between(
        lower: id,
        upper: id,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      idNotEqualTo(Id id) {
    return QueryBuilder.apply(this, (query) {
      if (query.whereSort == Sort.asc) {
        return query
            .addWhereClause(
              IdWhereClause.lessThan(upper: id, includeUpper: false),
            )
            .addWhereClause(
              IdWhereClause.greaterThan(lower: id, includeLower: false),
            );
      } else {
        return query
            .addWhereClause(
              IdWhereClause.greaterThan(lower: id, includeLower: false),
            )
            .addWhereClause(
              IdWhereClause.lessThan(upper: id, includeUpper: false),
            );
      }
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      idGreaterThan(Id id, {bool include = false}) {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(
        IdWhereClause.greaterThan(lower: id, includeLower: include),
      );
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      idLessThan(Id id, {bool include = false}) {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(
        IdWhereClause.lessThan(upper: id, includeUpper: include),
      );
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      idBetween(
    Id lowerId,
    Id upperId, {
    bool includeLower = true,
    bool includeUpper = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(IdWhereClause.between(
        lower: lowerId,
        includeLower: includeLower,
        upper: upperId,
        includeUpper: includeUpper,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      dateTimeEqualTo(DateTime dateTime) {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(IndexWhereClause.equalTo(
        indexName: r'dateTime',
        value: [dateTime],
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      dateTimeNotEqualTo(DateTime dateTime) {
    return QueryBuilder.apply(this, (query) {
      if (query.whereSort == Sort.asc) {
        return query
            .addWhereClause(IndexWhereClause.between(
              indexName: r'dateTime',
              lower: [],
              upper: [dateTime],
              includeUpper: false,
            ))
            .addWhereClause(IndexWhereClause.between(
              indexName: r'dateTime',
              lower: [dateTime],
              includeLower: false,
              upper: [],
            ));
      } else {
        return query
            .addWhereClause(IndexWhereClause.between(
              indexName: r'dateTime',
              lower: [dateTime],
              includeLower: false,
              upper: [],
            ))
            .addWhereClause(IndexWhereClause.between(
              indexName: r'dateTime',
              lower: [],
              upper: [dateTime],
              includeUpper: false,
            ));
      }
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      dateTimeGreaterThan(
    DateTime dateTime, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(IndexWhereClause.between(
        indexName: r'dateTime',
        lower: [dateTime],
        includeLower: include,
        upper: [],
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      dateTimeLessThan(
    DateTime dateTime, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(IndexWhereClause.between(
        indexName: r'dateTime',
        lower: [],
        upper: [dateTime],
        includeUpper: include,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterWhereClause>
      dateTimeBetween(
    DateTime lowerDateTime,
    DateTime upperDateTime, {
    bool includeLower = true,
    bool includeUpper = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addWhereClause(IndexWhereClause.between(
        indexName: r'dateTime',
        lower: [lowerDateTime],
        includeLower: includeLower,
        upper: [upperDateTime],
        includeUpper: includeUpper,
      ));
    });
  }
}

extension BloodPressureRecordQueryFilter on QueryBuilder<BloodPressureRecord,
    BloodPressureRecord, QFilterCondition> {
  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      dateTimeEqualTo(DateTime value) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'dateTime',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      dateTimeGreaterThan(
    DateTime value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        include: include,
        property: r'dateTime',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      dateTimeLessThan(
    DateTime value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.lessThan(
        include: include,
        property: r'dateTime',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      dateTimeBetween(
    DateTime lower,
    DateTime upper, {
    bool includeLower = true,
    bool includeUpper = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.between(
        property: r'dateTime',
        lower: lower,
        includeLower: includeLower,
        upper: upper,
        includeUpper: includeUpper,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      diastolicEqualTo(int value) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'diastolic',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      diastolicGreaterThan(
    int value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        include: include,
        property: r'diastolic',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      diastolicLessThan(
    int value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.lessThan(
        include: include,
        property: r'diastolic',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      diastolicBetween(
    int lower,
    int upper, {
    bool includeLower = true,
    bool includeUpper = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.between(
        property: r'diastolic',
        lower: lower,
        includeLower: includeLower,
        upper: upper,
        includeUpper: includeUpper,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionIsNull() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(const FilterCondition.isNull(
        property: r'emotion',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionIsNotNull() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(const FilterCondition.isNotNull(
        property: r'emotion',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionEqualTo(
    String? value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'emotion',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionGreaterThan(
    String? value, {
    bool include = false,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        include: include,
        property: r'emotion',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionLessThan(
    String? value, {
    bool include = false,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.lessThan(
        include: include,
        property: r'emotion',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionBetween(
    String? lower,
    String? upper, {
    bool includeLower = true,
    bool includeUpper = true,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.between(
        property: r'emotion',
        lower: lower,
        includeLower: includeLower,
        upper: upper,
        includeUpper: includeUpper,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionStartsWith(
    String value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.startsWith(
        property: r'emotion',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionEndsWith(
    String value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.endsWith(
        property: r'emotion',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionContains(String value, {bool caseSensitive = true}) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.contains(
        property: r'emotion',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionMatches(String pattern, {bool caseSensitive = true}) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.matches(
        property: r'emotion',
        wildcard: pattern,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionIsEmpty() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'emotion',
        value: '',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      emotionIsNotEmpty() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        property: r'emotion',
        value: '',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      idEqualTo(Id value) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'id',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      idGreaterThan(
    Id value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        include: include,
        property: r'id',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      idLessThan(
    Id value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.lessThan(
        include: include,
        property: r'id',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      idBetween(
    Id lower,
    Id upper, {
    bool includeLower = true,
    bool includeUpper = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.between(
        property: r'id',
        lower: lower,
        includeLower: includeLower,
        upper: upper,
        includeUpper: includeUpper,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteIsNull() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(const FilterCondition.isNull(
        property: r'note',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteIsNotNull() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(const FilterCondition.isNotNull(
        property: r'note',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteEqualTo(
    String? value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'note',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteGreaterThan(
    String? value, {
    bool include = false,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        include: include,
        property: r'note',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteLessThan(
    String? value, {
    bool include = false,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.lessThan(
        include: include,
        property: r'note',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteBetween(
    String? lower,
    String? upper, {
    bool includeLower = true,
    bool includeUpper = true,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.between(
        property: r'note',
        lower: lower,
        includeLower: includeLower,
        upper: upper,
        includeUpper: includeUpper,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteStartsWith(
    String value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.startsWith(
        property: r'note',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteEndsWith(
    String value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.endsWith(
        property: r'note',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteContains(String value, {bool caseSensitive = true}) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.contains(
        property: r'note',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteMatches(String pattern, {bool caseSensitive = true}) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.matches(
        property: r'note',
        wildcard: pattern,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteIsEmpty() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'note',
        value: '',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      noteIsNotEmpty() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        property: r'note',
        value: '',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      pulseEqualTo(int value) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'pulse',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      pulseGreaterThan(
    int value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        include: include,
        property: r'pulse',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      pulseLessThan(
    int value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.lessThan(
        include: include,
        property: r'pulse',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      pulseBetween(
    int lower,
    int upper, {
    bool includeLower = true,
    bool includeUpper = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.between(
        property: r'pulse',
        lower: lower,
        includeLower: includeLower,
        upper: upper,
        includeUpper: includeUpper,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      systolicEqualTo(int value) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'systolic',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      systolicGreaterThan(
    int value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        include: include,
        property: r'systolic',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      systolicLessThan(
    int value, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.lessThan(
        include: include,
        property: r'systolic',
        value: value,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      systolicBetween(
    int lower,
    int upper, {
    bool includeLower = true,
    bool includeUpper = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.between(
        property: r'systolic',
        lower: lower,
        includeLower: includeLower,
        upper: upper,
        includeUpper: includeUpper,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementEqualTo(
    String value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'tags',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementGreaterThan(
    String value, {
    bool include = false,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        include: include,
        property: r'tags',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementLessThan(
    String value, {
    bool include = false,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.lessThan(
        include: include,
        property: r'tags',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementBetween(
    String lower,
    String upper, {
    bool includeLower = true,
    bool includeUpper = true,
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.between(
        property: r'tags',
        lower: lower,
        includeLower: includeLower,
        upper: upper,
        includeUpper: includeUpper,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementStartsWith(
    String value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.startsWith(
        property: r'tags',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementEndsWith(
    String value, {
    bool caseSensitive = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.endsWith(
        property: r'tags',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementContains(String value, {bool caseSensitive = true}) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.contains(
        property: r'tags',
        value: value,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementMatches(String pattern, {bool caseSensitive = true}) {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.matches(
        property: r'tags',
        wildcard: pattern,
        caseSensitive: caseSensitive,
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementIsEmpty() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.equalTo(
        property: r'tags',
        value: '',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsElementIsNotEmpty() {
    return QueryBuilder.apply(this, (query) {
      return query.addFilterCondition(FilterCondition.greaterThan(
        property: r'tags',
        value: '',
      ));
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsLengthEqualTo(int length) {
    return QueryBuilder.apply(this, (query) {
      return query.listLength(
        r'tags',
        length,
        true,
        length,
        true,
      );
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsIsEmpty() {
    return QueryBuilder.apply(this, (query) {
      return query.listLength(
        r'tags',
        0,
        true,
        0,
        true,
      );
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsIsNotEmpty() {
    return QueryBuilder.apply(this, (query) {
      return query.listLength(
        r'tags',
        0,
        false,
        999999,
        true,
      );
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsLengthLessThan(
    int length, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.listLength(
        r'tags',
        0,
        true,
        length,
        include,
      );
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsLengthGreaterThan(
    int length, {
    bool include = false,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.listLength(
        r'tags',
        length,
        include,
        999999,
        true,
      );
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterFilterCondition>
      tagsLengthBetween(
    int lower,
    int upper, {
    bool includeLower = true,
    bool includeUpper = true,
  }) {
    return QueryBuilder.apply(this, (query) {
      return query.listLength(
        r'tags',
        lower,
        includeLower,
        upper,
        includeUpper,
      );
    });
  }
}

extension BloodPressureRecordQueryObject on QueryBuilder<BloodPressureRecord,
    BloodPressureRecord, QFilterCondition> {}

extension BloodPressureRecordQueryLinks on QueryBuilder<BloodPressureRecord,
    BloodPressureRecord, QFilterCondition> {}

extension BloodPressureRecordQuerySortBy
    on QueryBuilder<BloodPressureRecord, BloodPressureRecord, QSortBy> {
  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByDateTime() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'dateTime', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByDateTimeDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'dateTime', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByDiastolic() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'diastolic', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByDiastolicDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'diastolic', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByEmotion() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'emotion', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByEmotionDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'emotion', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByNote() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'note', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByNoteDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'note', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByPulse() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'pulse', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortByPulseDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'pulse', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortBySystolic() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'systolic', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      sortBySystolicDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'systolic', Sort.desc);
    });
  }
}

extension BloodPressureRecordQuerySortThenBy
    on QueryBuilder<BloodPressureRecord, BloodPressureRecord, QSortThenBy> {
  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByDateTime() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'dateTime', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByDateTimeDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'dateTime', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByDiastolic() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'diastolic', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByDiastolicDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'diastolic', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByEmotion() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'emotion', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByEmotionDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'emotion', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenById() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'id', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByIdDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'id', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByNote() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'note', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByNoteDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'note', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByPulse() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'pulse', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenByPulseDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'pulse', Sort.desc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenBySystolic() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'systolic', Sort.asc);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QAfterSortBy>
      thenBySystolicDesc() {
    return QueryBuilder.apply(this, (query) {
      return query.addSortBy(r'systolic', Sort.desc);
    });
  }
}

extension BloodPressureRecordQueryWhereDistinct
    on QueryBuilder<BloodPressureRecord, BloodPressureRecord, QDistinct> {
  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QDistinct>
      distinctByDateTime() {
    return QueryBuilder.apply(this, (query) {
      return query.addDistinctBy(r'dateTime');
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QDistinct>
      distinctByDiastolic() {
    return QueryBuilder.apply(this, (query) {
      return query.addDistinctBy(r'diastolic');
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QDistinct>
      distinctByEmotion({bool caseSensitive = true}) {
    return QueryBuilder.apply(this, (query) {
      return query.addDistinctBy(r'emotion', caseSensitive: caseSensitive);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QDistinct>
      distinctByNote({bool caseSensitive = true}) {
    return QueryBuilder.apply(this, (query) {
      return query.addDistinctBy(r'note', caseSensitive: caseSensitive);
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QDistinct>
      distinctByPulse() {
    return QueryBuilder.apply(this, (query) {
      return query.addDistinctBy(r'pulse');
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QDistinct>
      distinctBySystolic() {
    return QueryBuilder.apply(this, (query) {
      return query.addDistinctBy(r'systolic');
    });
  }

  QueryBuilder<BloodPressureRecord, BloodPressureRecord, QDistinct>
      distinctByTags() {
    return QueryBuilder.apply(this, (query) {
      return query.addDistinctBy(r'tags');
    });
  }
}

extension BloodPressureRecordQueryProperty
    on QueryBuilder<BloodPressureRecord, BloodPressureRecord, QQueryProperty> {
  QueryBuilder<BloodPressureRecord, int, QQueryOperations> idProperty() {
    return QueryBuilder.apply(this, (query) {
      return query.addPropertyName(r'id');
    });
  }

  QueryBuilder<BloodPressureRecord, DateTime, QQueryOperations>
      dateTimeProperty() {
    return QueryBuilder.apply(this, (query) {
      return query.addPropertyName(r'dateTime');
    });
  }

  QueryBuilder<BloodPressureRecord, int, QQueryOperations> diastolicProperty() {
    return QueryBuilder.apply(this, (query) {
      return query.addPropertyName(r'diastolic');
    });
  }

  QueryBuilder<BloodPressureRecord, String?, QQueryOperations>
      emotionProperty() {
    return QueryBuilder.apply(this, (query) {
      return query.addPropertyName(r'emotion');
    });
  }

  QueryBuilder<BloodPressureRecord, String?, QQueryOperations> noteProperty() {
    return QueryBuilder.apply(this, (query) {
      return query.addPropertyName(r'note');
    });
  }

  QueryBuilder<BloodPressureRecord, int, QQueryOperations> pulseProperty() {
    return QueryBuilder.apply(this, (query) {
      return query.addPropertyName(r'pulse');
    });
  }

  QueryBuilder<BloodPressureRecord, int, QQueryOperations> systolicProperty() {
    return QueryBuilder.apply(this, (query) {
      return query.addPropertyName(r'systolic');
    });
  }

  QueryBuilder<BloodPressureRecord, List<String>, QQueryOperations>
      tagsProperty() {
    return QueryBuilder.apply(this, (query) {
      return query.addPropertyName(r'tags');
    });
  }
}
