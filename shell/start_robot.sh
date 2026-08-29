#!/bin/bash

# ==========================================
# Orquestrador UR3 + Antigravity MCP
# ==========================================

# 1. Navega para a raiz do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "📂 Diretório de trabalho ajustado para: $PROJECT_ROOT"
cd "$PROJECT_ROOT" || exit 1

# "newgrp docker" sozinho não afeta os comandos seguintes de um script:
# ele abre um subshell à parte e, como ninguém interage com ele aqui, retorna
# na hora sem repassar a permissão. Por isso reexecutamos o próprio script
# já dentro do grupo "docker" (equivalente não interativo do newgrp).
if ! groups | grep -qw docker; then
    echo "🔑 Ativando o grupo 'docker' para esta sessão (reexecutando o script)..."
    exec sg docker "$0 $*"
fi

echo "🤖 Preparando o ecossistema UR3..."

# 2. Iniciar o driver do UR3 em um NOVO TERMINAL
echo "📡 Lançando o driver ROS2 em uma nova janela..."
gnome-terminal -- bash -ic "source /opt/ros/humble/setup.bash && ros2 launch ur_robot_driver ur_control.launch.py ur_type:=ur3 robot_ip:=192.168.1.102 launch_rviz:=true; exec bash"

echo "⏳ Aguardando 5 segundos para estabilização do ROS2..."
sleep 5

# 3. Levantar a infraestrutura Docker (ros-mcp-server + Rosbridge)
echo "🛡️ Verificando segurança e conflitos de contêiner..."

if docker ps -a --format '{{.Names}}' | grep -Eq "^ros-mcp-server$"; then
    BACKUP_NAME="ros-mcp-server_bkp_$(date +%Y%m%d_%H%M%S)"
    echo "⚠️ ATENÇÃO: Um contêiner 'ros-mcp-server' preexistente foi encontrado!"
    echo "📦 Renomeando para '$BACKUP_NAME' para evitar perda de dados..."
    docker rename ros-mcp-server "$BACKUP_NAME"
fi

if docker ps -a --format '{{.Names}}' | grep -Eq "^rosbridge$"; then
    BACKUP_NAME="rosbridge_bkp_$(date +%Y%m%d_%H%M%S)"
    docker rename rosbridge "$BACKUP_NAME"
fi

echo "🐳 Subindo os serviços do Docker Compose (ros-mcp-server + rosbridge)..."
docker compose up -d

echo "⏳ Aguardando 3 segundos para os contêineres inicializarem..."
sleep 3

# 4. Rodar o Antigravity diretamente no host (agy não está mais em container)
echo "🧠 Conectando ao Agente Autônomo (host)..."
echo "--------------------------------------------------------"

agy

echo "--------------------------------------------------------"

# 5. Encerramento limpo e seguro
echo "🛑 Encerrando o sistema..."
echo "Derrubando os contêineres Docker..."
docker compose down

echo "Desligando a árvore de processos do driver UR3..."
# Caça todos os processos filhos relacionados a este launch file específico
pkill -SIGINT -f "ur_control.launch.py"

echo "✅ Sistema encerrado com segurança."