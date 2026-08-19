#!/bin/bash

# ==========================================
# Orquestrador UR3 + Antigravity MCP
# ==========================================

# 1. Navega para a raiz do projeto (onde está o docker-compose.yml)
# Isso garante que o script funcione independente de onde você o chame no terminal
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "📂 Diretório de trabalho ajustado para: $PROJECT_ROOT"
cd "$PROJECT_ROOT" || exit 1

echo "🤖 Preparando o ecossistema UR3..."

# 2. Iniciar o driver do UR3 físico no host
echo "📡 Lançando o driver ROS2 (IP: 192.168.1.102)..."
nohup ros2 launch ur_robot_driver ur_control.launch.py \
      ur_type:=ur3 \
      robot_ip:=192.168.1.102 \
      launch_rviz:=true > ur3_driver.log 2>&1 &

ROS_PID=$!

echo "⏳ Aguardando 5 segundos para estabilização do ROS2..."
sleep 5

# 3. Levantar a infraestrutura Docker (Antigravity + Rosbridge) em background
echo "🛡️ Verificando segurança e conflitos de contêiner..."

# Checa se existe um contêiner chamado exatamente 'antigravity-mcp'
if docker ps -a --format '{{.Names}}' | grep -Eq "^antigravity-mcp$"; then
    # Gera um nome de backup com a data e hora atual
    BACKUP_NAME="antigravity-mcp_bkp_$(date +%Y%m%d_%H%M%S)"
    echo "⚠️ ATENÇÃO: Um contêiner 'antigravity-mcp' preexistente foi encontrado!"
    echo "📦 Renomeando para '$BACKUP_NAME' para evitar perda de dados..."
    docker rename antigravity-mcp "$BACKUP_NAME"
fi

# Faz a mesma proteção para o rosbridge, se necessário
if docker ps -a --format '{{.Names}}' | grep -Eq "^rosbridge$"; then
    BACKUP_NAME="rosbridge_bkp_$(date +%Y%m%d_%H%M%S)"
    docker rename rosbridge "$BACKUP_NAME"
fi

echo "🐳 Subindo os serviços do Docker Compose..."
docker compose up -d

echo "⏳ Aguardando 3 segundos para os contêineres inicializarem..."
sleep 3

# 4. Entrar na interface interativa do Antigravity
echo "🧠 Conectando ao Agente Autônomo..."
echo "--------------------------------------------------------"

# Executa o CLI do agente
docker exec -it antigravity-mcp agy 

echo "--------------------------------------------------------"

# 5. Encerramento limpo e seguro ao sair do agente
echo "🛑 Encerrando o sistema..."
echo "Derrubando os contêineres..."
docker compose down

echo "Desligando driver do UR3 (PID: $ROS_PID)..."
kill $ROS_PID

echo "✅ Sistema encerrado com segurança."
