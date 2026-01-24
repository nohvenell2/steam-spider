# Steam-Spider

Steam 플랫폼의 게임 데이터를 수집하는 분산 크롤링 시스템입니다.

## 프로젝트 개요

Steam의 전체 게임(약 140,000개) 정보를 수집하여 데이터베이스에 구축하는 **Producer-Consumer 패턴** 기반의 분산 처리 시스템입니다.

## 시스템 아키텍처

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Producer   │────▶│    Redis    │◀────│   Worker    │────▶│    Redis    │
│  & Monitor  │     │ (work queue)│     │  (Crawler)  │     │(result queue)│
└─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                   │
                                                                   ▼
                                                            ┌─────────────┐
                                                            │  DB Writer  │
                                                            └──────┬──────┘
                                                                   │
                                                                   ▼
                                                            ┌─────────────┐
                                                            │ PostgreSQL  │
                                                            └─────────────┘
```

## 기술 스택

| 구분 | 기술 |
|------|------|
| Language | Python 3.11+ |
| Message Broker | Redis |
| Database | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 |
| Container | Docker Compose |

## 컴포넌트

### [database/](database/)
PostgreSQL 데이터베이스 스키마 및 ORM 모델을 관리합니다.
- 게임 정보 테이블 스키마 정의 (basic_info, genres, tags, reviews)
- CRUD 함수 제공
- Docker Compose를 통한 PostgreSQL/Redis 환경 구성

### [producer_monitor/](producer_monitor/)
작업 생성 및 시스템 모니터링을 담당합니다.
- Steam Web API를 통해 전체 게임 ID 목록 수집
- Redis 작업 큐에 크롤링 대상 ID 적재
- 실시간 웹 대시보드로 큐 상태 및 진행률 모니터링

### [dbwriter/](dbwriter/)
크롤링된 데이터를 데이터베이스에 저장합니다.
- Redis 결과 큐에서 데이터 수신
- Batch 단위(100개) 또는 타임아웃(10초) 기준 Bulk Insert
- 데이터 유실 방지 메커니즘 (BRPOPLPUSH + LREM 패턴)

### Worker (외부)
실제 Steam 페이지를 크롤링하는 컴포넌트입니다.
- 분리된 환경에서 독립적으로 실행
- Redis 작업 큐에서 게임 ID를 가져와 크롤링 수행
- 결과 데이터를 JSON 형태로 Redis 결과 큐에 전송
- 본 프로젝트에 포함되지 않음

## 데이터 흐름

1. **Producer**: Steam API에서 게임 ID 목록 수집 → Redis 작업 큐에 적재
2. **Worker**: 작업 큐에서 ID 획득 → Steam 페이지 크롤링 → 결과 큐에 JSON 전송
3. **DB Writer**: 결과 큐에서 데이터 수집 → PostgreSQL에 Bulk Insert
4. **Monitor**: 전체 파이프라인 상태를 실시간 모니터링

## 빠른 시작

### 1. 인프라 실행
```bash
docker-compose up -d
```

### 2. Producer 실행
```bash
cd producer_monitor
poetry install
poetry run python -m src.producer.main --sample 10  # 테스트
```

### 3. DB Writer 실행
```bash
cd dbwriter
poetry install
poetry run dbwriter
```

### 4. 모니터링 대시보드
```bash
cd producer_monitor
poetry run producer-dashboard
# http://localhost:8080 접속
```

## 라이선스

MIT License
