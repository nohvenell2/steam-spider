# Steam-Spider Database Module

## 모듈 개요

이 모듈은 **Steam-Spider** 프로젝트의 데이터베이스 계층을 담당하는 하위 프로젝트입니다.

### 주요 역할
- **PostgreSQL 데이터베이스 스키마 정의 및 관리**
- **SQLAlchemy ORM 모델 제공** (basic_info, genres, tags, reviews)
- **CRUD 함수 제공** (다른 모듈에서 재사용 가능)
- **다중 프로젝트 접근 지원** (Frontend, Embedding, Crawler 등)
- **Redis 연결 테스트** (Message Broker 준비)

## 기술 스택

| 구분 | 기술 | 버전 | 용도 |
|------|------|------|------|
| Language | Python | 3.11+ | 메인 개발 언어 |
| Package Manager | Poetry | - | 의존성 관리 |
| Message Broker | Redis | 7.x | 작업 큐 및 결과 버퍼 |
| Database | PostgreSQL | 15.x | 게임 데이터 영구 저장 |
| ORM | SQLAlchemy | 2.0+ | 데이터베이스 ORM |
| Container | Docker Compose | - | PostgreSQL + Redis + DB 초기화 관리 |
| Testing | pytest | 7.x | 테스트 프레임워크 |

## 아키텍처 결정 사항

### PostgreSQL 선택 이유
- **다중 프로젝트 접근**: Frontend, Embedding, Crawler 등 여러 프로젝트에서 네트워크를 통해 동시 접속
- **동시성 제어**: 여러 클라이언트의 동시 읽기/쓰기 지원
- **대규모 데이터 처리**: 약 140,000개의 게임 데이터를 안정적으로 관리
- **트랜잭션 지원**: 강력한 ACID 속성 보장

### 모듈화 전략
이 데이터베이스 모듈은 독립적으로 개발 및 테스트되며, 다른 프로젝트에서 패키지로 import하여 사용할 수 있도록 설계되었습니다.

## 데이터베이스 스키마

### SQLAlchemy ORM 모델

#### 1. BasicInfo (basic_info 테이블)
게임의 기본 정보를 저장합니다.

```python
class BasicInfo(Base):
    __tablename__ = "basic_info"

    game_id = Column(Integer, primary_key=True)
    url = Column(String(500), nullable=False)
    title = Column(String(500))
    description = Column(Text)
    header_image = Column(String(500))
    developer = Column(String(200))
    publisher = Column(String(200))
    release_date = Column(DateTime, nullable=True)
    release_date_original = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    genres = relationship("Genre", cascade="all, delete-orphan")
    tags = relationship("Tag", cascade="all, delete-orphan")
    reviews = relationship("Review", uselist=False, cascade="all, delete-orphan")
```

#### 2. Genre (genres 테이블)
게임의 장르 정보 (Many-to-Many)

```python
class Genre(Base):
    __tablename__ = "genres"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("basic_info.game_id", ondelete="CASCADE"))
    genre_name = Column(String(100), nullable=False)

    # Unique constraint: (game_id, genre_name)
```

#### 3. Tag (tags 테이블)
사용자 정의 태그 (Many-to-Many)

```python
class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("basic_info.game_id", ondelete="CASCADE"))
    tag_name = Column(String(100), nullable=False)

    # Unique constraint: (game_id, tag_name)
```

#### 4. Review (reviews 테이블)
게임의 리뷰 통계 (1:1 with BasicInfo)

```python
class Review(Base):
    __tablename__ = "reviews"

    game_id = Column(Integer, ForeignKey("basic_info.game_id", ondelete="CASCADE"), primary_key=True)
    total_review_count = Column(Integer)
    all_reviews = Column(String(100))
    total_review_positive_percent = Column(Integer)
    recent_review_count = Column(Integer)
    recent_reviews = Column(String(100))
    recent_review_positive_percent = Column(Integer)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
```

## 프로젝트 구조

```
database/
├── README.md                 # 이 파일 (개발 가이드)
├── pyproject.toml            # Poetry 의존성 정의
├── poetry.lock               # 의존성 버전 lock
├── docker-compose.yml        # PostgreSQL + Redis + DB Init 설정
├── Dockerfile                # DB 초기화용 Multi-stage 이미지
├── entrypoint.sh             # DB 초기화 스크립트
├── init_db.py                # 테이블 생성 스크립트
├── .gitignore                # Git 제외 파일
│
├── src/
│   ├── __init__.py
│   └── db/
│       ├── __init__.py
│       ├── models.py         # SQLAlchemy ORM 모델
│       ├── connection.py     # PostgreSQL 연결 및 세션 관리
│       └── crud.py           # CRUD 함수
│
└── data/
    └── .gitkeep
```

## 환경 설정

### 1. Poetry 의존성 설치

```bash
poetry install
```

### 2. Docker Compose로 PostgreSQL + Redis 실행 및 자동 초기화

```bash
# PostgreSQL, Redis 실행 + 테이블 자동 생성
docker-compose up -d

# 초기화 로그 확인
docker-compose logs db-init
```

**컨테이너 정보:**
- PostgreSQL: `localhost:5432`
  - Database: `steam_games`
  - User: `steam_user`
  - Password: `steam_password`
- Redis: `localhost:6379`
  - Password: `redis_password`
- DB Init: 자동으로 테이블 생성 후 종료

**자동 초기화 특징:**
- PostgreSQL이 준비될 때까지 대기
- 모든 테이블 자동 생성 (이미 존재하면 생략)
- 초기화 완료 후 컨테이너 자동 종료
- 실패 시 에러 로그 출력

### 3. 수동 데이터베이스 초기화 (선택사항)

Docker 없이 로컬에서 테이블을 생성하려면:

```bash
# init_db.py 스크립트 실행
python init_db.py
```

또는 Python 코드에서:

```python
from src.db.connection import init_db

# 테이블 생성
init_db()
```

### 4. Docker 이미지 최적화

현재 Docker 이미지는 Multi-stage build를 사용하여 최적화되었습니다:

**최적화 전략:**
- Stage 1 (Builder): Poetry를 사용하여 의존성을 requirements.txt로 export
- Stage 2 (Runtime): 최소한의 런타임 의존성만 포함
- 불필요한 크롤링 라이브러리 제거 (requests, beautifulsoup4, lxml, alembic)

**최종 이미지 크기:** ~200MB (Poetry와 빌드 도구 제외)

### 5. 환경변수 설정 (선택사항)

`.env` 파일 생성:
```bash
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=steam_games
POSTGRES_USER=steam_user
POSTGRES_PASSWORD=steam_password

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=redis_password
```

## 사용 예제

### 데이터 삽입

```python
from src.db.connection import get_session_context
from src.db.crud import insert_game_data

# 크롤러에서 받은 데이터
game_info = {
    "game_id": 1091500,
    "url": "https://store.steampowered.com/app/1091500",
    "title": "Cyberpunk 2077",
    "description": "Cyberpunk 2077 is an open-world RPG...",
    "header_image": "https://cdn.akamai.steamstatic.com/...",
    "genres": ["RPG", "Action"],
    "developer": "CD PROJEKT RED",
    "publisher": "CD PROJEKT RED",
    "release_date": "9 Dec, 2020",  # DB Writer가 DateTime으로 파싱
    "tags": ["Cyberpunk", "Open World", "Futuristic"],
    "reviews": {
        "total_review_count": 641535,
        "all_reviews": "Very Positive",
        "total_review_positive_percent": 86,
        "recent_review_count": 12450,
        "recent_reviews": "Very Positive",
        "recent_review_positive_percent": 91
    }
}

# Context manager로 자동 commit/rollback
with get_session_context() as session:
    game = insert_game_data(session, game_info)
    print(f"Inserted: {game.title}")
```

### 데이터 조회

```python
from src.db.connection import get_session_context
from src.db.crud import get_game_by_id, get_games_by_genre

with get_session_context() as session:
    # 게임 ID로 조회
    game = get_game_by_id(session, 1091500)
    if game:
        print(f"Title: {game['title']}")
        print(f"Genres: {game['genres']}")
        print(f"Reviews: {game['reviews']}")

    # 장르로 조회
    rpg_games = get_games_by_genre(session, "RPG", limit=10)
    for game in rpg_games:
        print(game['title'])
```

### 벌크 삽입

```python
from src.db.connection import get_session_context
from src.db.crud import bulk_insert_games

games_data = [game_info1, game_info2, game_info3, ...]

with get_session_context() as session:
    count = bulk_insert_games(session, games_data)
    print(f"Inserted {count} games")
```

## CRUD 함수 목록

### 기본 함수
- `insert_game_data(session, game_info)` - 게임 데이터 삽입/업데이트
- `get_game_by_id(session, game_id)` - 게임 ID로 조회
- `game_exists(session, game_id)` - 게임 존재 여부 확인
- `get_all_game_ids(session)` - 모든 게임 ID 조회
- `get_games_count(session)` - 총 게임 수
- `delete_game(session, game_id)` - 게임 삭제 (cascade)

### 고급 함수
- `get_games_by_genre(session, genre_name, limit)` - 장르로 검색
- `get_games_by_tag(session, tag_name, limit)` - 태그로 검색
- `bulk_insert_games(session, games_data)` - 벌크 삽입

## 데이터 인터페이스

### 입력 데이터 형식
CRUD 함수는 다음과 같은 딕셔너리 형식의 게임 데이터를 받습니다:

```python
{
    "game_id": int,
    "url": str,
    "title": str,
    "description": str,
    "header_image": str,
    "genres": list,          # ["Action", "RPG", ...]
    "developer": str,
    "publisher": str,
    "release_date": str,     # DB Writer가 DateTime으로 파싱 (예: "25 Feb, 2022")
                             # 원본 텍스트는 release_date_original에 저장
    "tags": list,            # ["Singleplayer", "Atmospheric", ...]
    "reviews": {
        "total_review_count": int,
        "all_reviews": str,
        "total_review_positive_percent": int,
        "recent_review_count": int,
        "recent_reviews": str,
        "recent_review_positive_percent": int
    }
}
```

이 형식은 크롤러 모듈의 출력과 일치하도록 설계되었습니다.

## Redis 준비 상태

현재 단계에서는 Redis 연결 테스트만 수행합니다.
Redis는 다음 단계에서 Message Broker로 활용될 예정입니다:

- `queue:work` (List): 처리할 Game ID 대기열
- `queue:result` (List): 크롤링 완료된 데이터
- `set:completed` (Set): 처리 완료된 ID 집합

Redis 테스트는 [tests/test_redis.py](tests/test_redis.py)에서 확인할 수 있습니다.