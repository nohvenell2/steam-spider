FROM postgres:15-alpine

# clang, llvm을 빼고, make 옵션에 with_llvm=no 를 추가합니다.
RUN apk update && apk add --no-cache build-base git \
    && git clone --branch v0.6.0 https://github.com/pgvector/pgvector.git \
    && cd pgvector \
    && make with_llvm=no \
    && make install with_llvm=no \
    && cd .. \
    && rm -rf pgvector \
    && apk del build-base git