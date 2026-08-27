#!/bin/bash
set -e

# Script de Entrypoint para o Antigravity CLI
# Este script resolve o problema de o volume esconder o settings.json

GEMINI_CONFIG_DIR="/root/.gemini"
SETTINGS_FILE="$GEMINI_CONFIG_DIR/settings.json"

echo "🚀 Iniciando Antigravity-MCP Entrypoint..."

# Garantir que o diretório de configuração existe
mkdir -p "$GEMINI_CONFIG_DIR"

# Criar ou atualizar o settings.json caso ele não tenha o servidor ROS configurado
# Isso garante que mesmo se o volume estiver vazio, a configuração seja injetada
if [ ! -f "$SETTINGS_FILE" ] || ! grep -q "ros-mcp-server" "$SETTINGS_FILE"; then
    echo "📝 Configurando servidor ROS MCP em $SETTINGS_FILE..."
    
    # Criamos um JSON básico. Se o arquivo já existe, poderíamos usar jq para mergear,
    # mas para manter offline-friendly sem jq, vamos sobrescrever com a configuração necessária.
    echo '{
      "mcpServers": {
        "ros-mcp-server": {
          "command": "ros-mcp",
          "args": ["--transport=stdio"]
        }
      }
    }' > "$SETTINGS_FILE"
fi

echo "✅ Configuração verificada."

# Se o comando for 'antigravity', executamos ele. 
# Se não houver argumentos, mantemos o container vivo.
if [ "$#" -eq 0 ]; then
    echo "😴 Nenhum comando fornecido. Mantendo container ativo (IDLE mode)..."
    echo "DICA: Use 'docker exec -it antigravity-mcp bash' para interagir."
    tail -f /dev/null
else
    echo "🏃 Executando: agy $@"
    exec agy "$@"
fi
