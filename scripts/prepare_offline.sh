#!/bin/bash
set -e

# Script para preparar o bundle offline usando containers
echo "📦 Iniciando preparação do bundle offline via Docker..."

# Criar pastas necessárias
mkdir -p vendor/apt-ubuntu vendor/apt-ros vendor/npm vendor/python/wheels vendor/images vendor/bin

# 1. Download das Imagens Docker Base
echo "🐳 Fazendo pull das imagens base..."
docker pull ubuntu:22.04
docker pull ros:humble-ros-base
docker pull python:3.10-bookworm
docker pull node:20-slim

echo "💾 Salvando imagens em .tar (Isso pode demorar alguns minutos)..."
docker save ubuntu:22.04 -o vendor/images/ubuntu_22.04.tar
docker save ros:humble-ros-base -o vendor/images/ros_humble.tar

# 2. Baixando Node.js Binário estático
echo "📥 Baixando binário estático do Node.js..."
if [ ! -f vendor/bin/node.tar.xz ]; then
    curl -sL -o vendor/bin/node.tar.xz https://nodejs.org/dist/v20.12.2/node-v20.12.2-linux-x64.tar.xz
fi

# 3. APT Repo local para Ubuntu
echo "📥 Criando repo APT offline para Ubuntu..."
docker run --rm -v $(pwd)/vendor/apt-ubuntu:/out ubuntu:22.04 bash -c "
    apt-get update && apt-get install -y dpkg-dev && \
    packages='python3 python3-pip python3-venv git build-essential libgl1 libglib2.0-0 xz-utils' && \
    cd /tmp && \
    # Coleta todas as dependências recursivamente
    all_packages=\$(apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances \$packages | grep '^\w' | sort -u) && \
    echo 'Baixando todos os pacotes e dependências...' && \
    apt-get download \$all_packages 2>/dev/null || true && \
    # Também tenta o download normal das dependências via cache para garantir
    apt-get install -y --download-only -o APT::Sandbox::User=root \$packages && \
    cp /var/cache/apt/archives/*.deb /out/ 2>/dev/null || true && \
    mv *.deb /out/ 2>/dev/null || true && \
    cd /out && dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz"

# 4. APT Repo local para ROS
echo "📥 Criando repo APT offline para ROS..."
docker run --rm -v $(pwd)/vendor/apt-ros:/out ros:humble-ros-base bash -c "
    apt-get update && apt-get install -y dpkg-dev && \
    packages='ros-humble-rosbridge-suite ros-humble-rmw-cyclonedds-cpp' && \
    cd /tmp && \
    all_packages=\$(apt-cache depends --recurse --no-recommends --no-suggests --no-conflicts --no-breaks --no-replaces --no-enhances \$packages | grep '^\w' | sort -u) && \
    echo 'Baixando todos os pacotes e dependências ROS...' && \
    apt-get download \$all_packages 2>/dev/null || true && \
    apt-get install -y --download-only -o APT::Sandbox::User=root \$packages && \
    cp /var/cache/apt/archives/*.deb /out/ 2>/dev/null || true && \
    mv *.deb /out/ 2>/dev/null || true && \
    cd /out && dpkg-scanpackages . /dev/null | gzip -9c > Packages.gz"

# 5. Download do binário oficial do Antigravity CLI (agy)
echo "🛠️ Baixando o binário do Antigravity CLI..."
docker run --rm -v $(pwd)/vendor/bin:/out ubuntu:22.04 bash -c "
    apt-get update && apt-get install -y curl ca-certificates && \
    curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /out"

# 6. Python Wheels (ROS MCP Server e UV)
# Resolve o erro do executável UV ausente e dependências de build
echo "🐍 Baixando dependências Python (incluindo UV e build-system)..."
docker run --rm -v $(pwd):/app -w /app python:3.10-bookworm bash -c "
    pip install uv && \
    uv pip compile ros-mcp-server/pyproject.toml -o vendor/python/requirements.txt && \
    pip download -r vendor/python/requirements.txt -d vendor/python/wheels/ && \
    pip download uv setuptools wheel -d vendor/python/wheels/"

echo "✅ TUDO PRONTO!"
echo "Transfira o projeto inteiro para a máquina offline e rode:"
echo "docker load -i vendor/images/ubuntu_22.04.tar"
echo "docker load -i vendor/images/ros_humble.tar"
echo "docker compose up --build -d"
