# 构建阶段
FROM rust:1.75-slim-bookworm AS builder

# 安装依赖
RUN apt-get update && apt-get install -y \
    pkg-config \
    libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制依赖文件
COPY Cargo.toml Cargo.lock ./

# 复制源代码
COPY src ./src

# 构建 release 版本
RUN cargo build --release

# 运行阶段
FROM debian:bookworm-slim

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    ca-certificates \
    libsqlite3-0 \
    iputils-ping \
    traceroute \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

# 安装 nexttrace (可选)
RUN apt-get update && apt-get install -y curl \
    && curl -sL https://github.com/nxtrace/NTrace-core/releases/latest/download/nexttrace_linux_amd64 -o /usr/local/bin/nexttrace \
    && chmod +x /usr/local/bin/nexttrace \
    && rm -rf /var/lib/apt/lists/* \
    && true

WORKDIR /app

# 复制构建产物
COPY --from=builder /app/target/release/tg-anti-harassment-bot /app/bot

# 创建数据目录
RUN mkdir -p /app/data

# 设置环境变量
ENV RUST_LOG=info

# 运行
CMD ["./bot"]
