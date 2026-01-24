# Steam-Spider DB Writer

DB Writer (Batch Processor) for Steam-Spider distributed crawler system.

## 개요

Redis `queue:result`에서 크롤링된 게임 데이터를 수신하여 PostgreSQL 데이터베이스에 bulk insert하는 배치 프로세서입니다.

### 주요 기능

- **데이터 유실 방지**: BRPOPLPUSH + LREM 패턴으로 크래시 시에도 데이터 안전 보장 ✨ NEW
- **Batch Processing**: 100개 단위 또는 10초 타임아웃으로 bulk insert 수행
- **Savepoint 기반 에러 핸들링**: 개별 게임 에러 시 해당 항목만 롤백, 나머지는 정상 저장
- **자동 데이터 검증 및 보정**: DB 제한 길이 초과 시 자동 truncate (에러 방지)
- **날짜 파싱**: 다국어 release_date 문자열(영어, 한글, 일본어 등)을 datetime으로 파싱
- **원본 데이터 보존**: 파싱 성공/실패 여부와 관계없이 원본 날짜 문자열을 DB에 저장
- **Timezone-aware Timestamps**: UTC 기준 생성/수정 시각 자동 관리
- **Redis Pipeline 최적화**: 배치 LREM 작업을 단일 네트워크 호출로 처리 ✨ NEW
- **에러 처리**: DB 연결 에러는 재시도, 데이터 검증 에러는 상세 로깅
- **Graceful Shutdown**: SIGINT/SIGTERM 시그널 처리로 안전한 종료
- **Connection Pooling**: PostgreSQL 연결 풀링으로 성능 최적화

## 의존성 관리

이 프로젝트는 **Poetry**를 사용하여 의존성을 관리합니다.

```bash
# 의존성 설치
poetry install

# 가상환경 활성화
poetry shell
```

## 환경 설정

`.env.example` 파일을 `.env`로 복사하고 환경에 맞게 수정하세요.

```bash
cp .env.example .env
```

### 주요 설정 항목

```bash
# Redis 설정
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# PostgreSQL 설정
POSTGRES_USER=steam_user
POSTGRES_PASSWORD=steam_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=steam_games

# 배치 처리 설정
BUFFER_SIZE=100          # 버퍼 크기
BUFFER_TIMEOUT=10        # 타임아웃 (초)

# 에러 처리 설정
MAX_DB_RETRIES=3         # DB 재시도 최대 횟수
RETRY_BASE_DELAY=1.0     # 재시도 기본 지연 (초)

# 로깅 설정
LOG_LEVEL=INFO           # 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
```

## 실행 방법

```bash
# Poetry 환경에서 실행
poetry run dbwriter

# 또는 가상환경 활성화 후 실행
poetry shell
python -m dbwriter.main
```

## 데이터 흐름

```
Redis queue:result
    ↓ BRPOPLPUSH (timeout=10s) → queue:saving에 메시지 이동 (원자적)
    ↓
JSON 파싱 (실패 시 queue:saving에 유지)
    ↓
DateParser (release_date 문자열 → datetime)
    ↓
Buffer 추가 (transformed data + raw JSON string)
    ↓
Flush 조건 체크 (100개 or 10초)
    ↓
Bulk Insert to PostgreSQL
    ├─ Savepoint 1 → Game 1 → Commit/Rollback
    ├─ Savepoint 2 → Game 2 → Commit/Rollback
    ├─ ...
    └─ Main Transaction Commit ✅
    ↓
Redis Pipeline LREM (queue:saving에서 배치 삭제)
    ├─ LREM 100개 메시지
    └─ 단일 네트워크 호출로 처리
    ↓
Success (메시지 안전하게 처리 완료)
```

### 데이터 유실 방지 메커니즘 ✨

**BRPOPLPUSH + LREM 패턴**을 사용하여 크래시 시에도 데이터가 유실되지 않습니다:

1. **메시지 이동**: `queue:result`에서 `queue:saving`으로 원자적 이동 (BRPOPLPUSH)
2. **안전한 버퍼링**: 메시지가 `queue:saving`에 보관된 상태로 처리
3. **DB 커밋 우선**: PostgreSQL에 완전히 저장된 후에만 다음 단계 진행
4. **배치 정리**: DB 저장 성공 시 Redis Pipeline으로 `queue:saving`에서 삭제 (LREM)

**크래시 시나리오별 안전성**:
- ✅ BRPOPLPUSH 후 크래시 → `queue:saving`에 메시지 유지 → 재시작 시 재처리
- ✅ 변환 중 크래시 → `queue:saving`에 메시지 유지 → 재시작 시 재처리
- ✅ DB 커밋 후 크래시 → `queue:saving`에 메시지 유지 → 재처리 시 upsert로 중복 방지
- ✅ LREM 중 크래시 → 일부만 삭제됨 → 나머지 재처리 시 upsert로 중복 방지

### Savepoint 기반 에러 핸들링

각 게임 데이터는 개별 savepoint(nested transaction)로 처리됩니다:

1. **정상 케이스**: 게임 삽입 성공 → savepoint commit → 다음 게임 처리
2. **에러 케이스**: 데이터 검증 실패 → savepoint rollback → 에러 로깅 → 다음 게임 계속 처리
3. **최종 커밋**: 모든 게임 처리 완료 후 메인 트랜잭션 한 번에 커밋

**장점**:
- title, developer 등의 길이 초과나 예상치 못한 데이터 에러가 발생해도 전체 배치가 실패하지 않음
- 실패한 게임의 ID와 에러 타입이 상세히 로깅되어 추적 가능
- 여전히 하나의 DB 연결로 처리되어 성능 효율적

## 날짜 파싱

### 지원 형식

- **영어**: "25 Feb, 2022", "Dec 9, 2020", "February 25, 2022"
- **한글**: "2020년 12월 10일"
- **일본어**: "2020年12月10日"
- **특수 케이스**: "Coming Soon", "TBA" → NULL

### 파싱 실패 처리

- release_date를 NULL로 저장
- 원본 문자열은 로그에 WARNING 레벨로 기록
- DB 스키마 수정 불필요

## 로깅

로그 파일은 `logs/` 디렉토리에 타임스탬프와 함께 저장됩니다.

```
logs/dbwriter_20260105_143022.log
```

### 로그 형식

```
[2026-01-05 14:30:22] DBWriter started | buffer_size=100 | timeout=10s
[2026-01-05 14:30:25] Buffer flushed | count=100 | duration=0.5s | total=1000
[2026-01-05 14:30:26] Date parse failed | game_id=1091500 | original='Coming Soon'
[2026-01-05 14:30:30] Graceful shutdown | total_processed=1234
```

## 프로젝트 구조

```
dbwriter/
├── src/
│   └── dbwriter/
│       ├── main.py              # 엔트리포인트
│       ├── batch_processor.py   # 배치 처리 로직
│       ├── date_parser.py       # 날짜 파싱
│       ├── config.py            # 설정 관리
│       ├── exceptions.py        # 커스텀 예외
│       └── db/                  # 데이터베이스 모듈
│           ├── models.py        # ORM 모델
│           ├── crud.py          # CRUD 함수
│           └── connection.py    # DB 연결 관리
├── tests/                       # 테스트 코드
├── logs/                        # 로그 파일 (자동 생성)
├── pyproject.toml               # Poetry 설정
├── .env.example                 # 환경변수 예시
└── README.md                    # 프로젝트 문서
```

## 관련 문서

- **프로젝트 전체 개요**: [Blueprint.md](Blueprint.md)
- **Worker 관련 정보**: [README-worker.md](README-worker.md)
- **데이터베이스 스키마**: [README-db.md](README-db.md)
- **Producer 관련 정보**: [README-producer.md](README-producer.md)
- **개발 가이드**: [CLAUDE.md](CLAUDE.md)

## 기술 스택

- **Python**: 3.11+
- **Redis**: 5.0+
- **PostgreSQL**: 15+
- **SQLAlchemy**: 2.0 (ORM)
- **python-dateutil**: 2.8.2 (날짜 파싱)

## 주의사항

- **독립 프로젝트**: database 모듈을 dbwriter 내부에 독립적으로 구현
- **향후 통합 고려**: producer, worker, dbwriter 통합 가능성을 고려한 설계
- **로깅**: 파싱 실패한 원본 문자열은 로그로만 기록 (DB에 저장하지 않음)
- **크롤링 Worker와 구분**: 메인 루프는 `consumer_loop`로 명명

## 운영 가이드

### Queue 모니터링

`queue:saving` 큐의 길이를 모니터링하여 시스템 상태를 확인할 수 있습니다:

```bash
# queue:saving 길이 확인
redis-cli llen queue:saving

# queue:saving 메시지 조회 (상위 10개)
redis-cli lrange queue:saving 0 10
```

**정상 상태**: `queue:saving` 길이가 0에 가까워야 합니다.
**주의 필요**: 길이가 지속적으로 증가하면 처리 속도보다 메시지 생성이 빠르거나 에러가 발생 중입니다.

## 라이선스

MIT License
