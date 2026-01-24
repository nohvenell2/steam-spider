# Redis TLS/SSL 보안 설정 가이드

이 문서는 SteamGrandProject에서 Redis TLS/SSL 연결을 설정하는 방법을 설명합니다.

## 개요

Redis TLS/SSL을 통해 다음과 같은 보안 이점을 얻을 수 있습니다:
- **데이터 암호화**: 네트워크를 통해 전송되는 모든 데이터가 암호화됩니다
- **중간자 공격 방지**: 패스워드와 게임 데이터가 안전하게 전송됩니다
- **인증 강화**: CA 인증서를 통한 서버 검증

## 구성 요소

### 1. 인증서 파일

프로젝트 루트의 `redis_certs/` 디렉토리에 다음 인증서가 포함되어 있습니다:

```
redis_certs/
├── ca-cert.pem       # CA 인증서 (클라이언트 검증용)
├── server-cert.pem   # Redis 서버 인증서
└── server-key.pem    # Redis 서버 개인키
```

**Worker용 인증서**: 외부에서 실행되는 Worker는 `worker/redis_certs/`에 CA 인증서 복사본이 필요합니다.

### 2. Redis 서버 설정

Redis는 TLS 전용 모드로 실행됩니다 ([redis_config/redis.conf](redis_config/redis.conf)):

```conf
# 일반 포트 비활성화
port 0

# TLS 포트 활성화
tls-port 6379
tls-cert-file /etc/redis/certs/server-cert.pem
tls-key-file /etc/redis/certs/server-key.pem
tls-ca-cert-file /etc/redis/certs/ca-cert.pem

# TLS 보안 설정
tls-auth-clients no
tls-protocols "TLSv1.2 TLSv1.3"
```

### 3. 환경 변수 설정

각 서비스의 `.env` 파일에 TLS 설정 추가:

```env
# Redis TLS/SSL Configuration
REDIS_SSL_ENABLED=true
REDIS_SSL_CA_CERT=/etc/redis/certs/ca-cert.pem
REDIS_SSL_CERT=
REDIS_SSL_KEY=
REDIS_SSL_CHECK_HOSTNAME=false
```

**설명**:
- `REDIS_SSL_ENABLED`: TLS 연결 활성화
- `REDIS_SSL_CA_CERT`: 서버 인증서 검증용 CA 인증서 경로
- `REDIS_SSL_CHECK_HOSTNAME`: 호스트 이름 검증 (내부 네트워크는 false)

## 서비스별 설정

### Producer Monitor

- **위치**: `producer_monitor/`
- **환경 변수**: `producer_monitor/.env`
- **코드**: [producer_monitor/src/producer/queue/redis_queue.py](producer_monitor/src/producer/queue/redis_queue.py:64-93)

### DB Writer

- **위치**: `dbwriter/`
- **환경 변수**: `dbwriter/.env`
- **코드**: [dbwriter/src/dbwriter/main.py](dbwriter/src/dbwriter/main.py:94-106)

### Worker

- **위치**: `worker/`
- **환경 변수**: `worker/.env`
- **인증서**: `worker/redis_certs/ca-cert.pem` (복사본)
- **코드**: [worker/worker/main.py](worker/worker/main.py:228-240)

## 테스트

### 1. Redis 컨테이너 확인

Redis가 TLS 모드로 실행되는지 확인:

```bash
docker logs redis | grep "Ready to accept connections"
# 출력: Ready to accept connections tls
```

### 2. Python 연결 테스트

프로젝트 루트에서 테스트 스크립트 실행:

```bash
cd c:/Git/SteamGrandProject
./producer_monitor/.venv/Scripts/python.exe test_redis_tls.py
```

**예상 출력**:
```
✓ Redis TLS connection successful!
✓ PING response: True
✓ Redis version: 7.4.7
```

### 3. redis-cli로 테스트

Docker 컨테이너 내부에서:

```bash
docker exec redis redis-cli \
  --tls \
  --cacert /etc/redis/certs/ca-cert.pem \
  --user admin_user \
  --pass 'password' \
  PING
```

### 4. 서비스 로그 확인

각 서비스가 TLS로 연결되는지 확인:

```bash
# DB Writer 로그
docker logs dbwriter | grep "TLS=enabled"

# Producer Monitor 로그
docker logs producer-monitor | grep "Enabling TLS"
```

## 문제 해결

### "Connection reset by peer" 오류

**원인**: TLS가 활성화된 Redis에 평문 연결 시도

**해결**:
1. `.env` 파일에서 `REDIS_SSL_ENABLED=true` 확인
2. 컨테이너 재시작: `docker-compose restart`

### "No such file or directory" (인증서 파일)

**원인**: 인증서 파일 경로가 잘못되었거나 볼륨 마운트 누락

**해결**:
1. [docker-compose.yml](docker-compose.yml)에서 볼륨 마운트 확인:
   ```yaml
   volumes:
     - ./redis_certs:/etc/redis/certs:ro
   ```
2. 인증서 파일 존재 확인:
   ```bash
   ls -la redis_certs/
   ```

### Worker 연결 실패

**원인**: Worker 디렉토리에 CA 인증서 누락

**해결**:
```bash
cp redis_certs/ca-cert.pem worker/redis_certs/
```

## TLS 비활성화 (개발용)

개발 중 TLS를 임시로 비활성화하려면:

1. `.env` 파일 수정:
   ```env
   REDIS_SSL_ENABLED=false
   ```

2. [redis_config/redis.conf](redis_config/redis.conf) 수정:
   ```conf
   port 6379
   tls-port 0
   ```

3. 컨테이너 재시작:
   ```bash
   docker-compose restart redis dbwriter producer-monitor
   ```

## 프로덕션 권장사항

### 1. 인증서 갱신

자체 서명 인증서는 만료 전에 갱신해야 합니다:

```bash
# 인증서 만료일 확인
openssl x509 -in redis_certs/server-cert.pem -noout -dates
```

### 2. 클라이언트 인증서 (양방향 TLS)

보안을 강화하려면 클라이언트 인증서도 사용:

1. 클라이언트 인증서 생성
2. [redis.conf](redis_config/redis.conf) 수정:
   ```conf
   tls-auth-clients yes
   ```
3. `.env`에 클라이언트 인증서 경로 추가:
   ```env
   REDIS_SSL_CERT=/etc/redis/certs/client-cert.pem
   REDIS_SSL_KEY=/etc/redis/certs/client-key.pem
   ```

### 3. 호스트 이름 검증

공개 도메인을 사용하는 경우:

```env
REDIS_SSL_CHECK_HOSTNAME=true
```

## 참고 자료

- [Redis TLS 공식 문서](https://redis.io/docs/manual/security/encryption/)
- [Python redis-py TLS 지원](https://redis-py.readthedocs.io/en/stable/connections.html#ssl-connections)
- 프로젝트 설정 파일:
  - [redis_config/redis.conf](redis_config/redis.conf)
  - [docker-compose.yml](docker-compose.yml)
  - [.env](.env)

## 요약

✅ **완료된 작업**:
1. Redis 서버 TLS 활성화 (포트 6379, TLS 전용)
2. 모든 Python 클라이언트에 TLS 지원 추가
3. 환경 변수를 통한 TLS 설정 관리
4. Docker 컨테이너에 인증서 볼륨 마운트
5. 서비스별 연결 테스트 성공

✅ **보안 개선**:
- 모든 Redis 통신이 TLS로 암호화됨
- 중간자 공격 방지
- CA 인증서를 통한 서버 검증
