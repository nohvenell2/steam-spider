# Steam-Spider Producer & Monitor

Steam 게임 데이터 수집 시스템의 Producer 및 Monitor 통합 프로젝트입니다.

## 개요

- **Producer**: Steam Web API에서 게임 ID를 가져와 Redis 큐에 작업 적재
- **Monitor**: Redis 큐와 PostgreSQL 데이터베이스 실시간 모니터링 대시보드

## 주요 기능

### Producer
- Steam API 연동 (140,000+ 게임)
- Redis 작업 큐 관리
- 배치 방식 작업 푸시
- 샘플 모드 테스트 지원

### Monitor Dashboard
- 실시간 큐 모니터링 (work, processing, result, dead)
- 진행률 계산 및 Progress Bar
- PostgreSQL 헬스 체크
- 웹 대시보드 (SSE 스트리밍)

## 설치

### 사전 요구사항
- Python 3.11+
- Poetry
- Redis 서버
- PostgreSQL 서버
- Steam Web API 키

### 의존성 설치
```bash
poetry install
```

### 환경 변수 설정
`.env` 파일을 생성하고 다음 내용을 추가합니다:
```env
# Steam API
STEAM_API_KEY=your_steam_api_key_here

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=redis_password

# PostgreSQL
POSTGRES_USER=steam_user
POSTGRES_PASSWORD=steam_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=steam_games

# Dashboard
DASHBOARD_HOST=localhost
DASHBOARD_PORT=8080
REFRESH_INTERVAL=2
LOG_LEVEL=INFO
```

## 사용법

### Producer 실행
```bash
# 테스트 모드
poetry run python -m src.producer.main --sample 10

# 프로덕션 모드
poetry run python -m src.producer.main
```

### Monitor Dashboard 실행
```bash
poetry run producer-dashboard
# http://localhost:8080 접속
```

### CLI 유틸리티
```bash
# Redis 초기화
poetry run producer-reset-redis

# PostgreSQL 초기화
poetry run producer-reset-db

# 전체 초기화
poetry run producer-reset-all

# Processing 큐 복구
poetry run producer-recover
```

## 프로젝트 구조
```
producer_monitor/
├── src/producer/
│   ├── main.py              # Producer 메인
│   ├── api/                 # Steam API
│   ├── queue/               # Redis 큐 관리
│   ├── dashboard/           # Monitor 대시보드
│   │   ├── app.py          # Flask 앱
│   │   ├── templates/      # HTML 템플릿
│   │   └── static/         # CSS, JavaScript
│   └── cli/                # 관리 유틸리티
└── tests/
```

## 라이선스
MIT
