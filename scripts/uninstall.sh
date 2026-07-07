#!/bin/bash
echo "🧹 Iniciando limpeza profunda do ambiente DockerRosGemini..."

# 1. Parar e remover todos os containers associados ao docker-compose local
echo "🛑 Parando containers..."
docker compose down -v || true

# 2. Remover o volume nomeado que guarda a configuração (muito importante)
echo "🗑️ Removendo volume gemini-config antigo..."
docker volume rm dockerrosgemini_gemini-config 2>/dev/null || true

# 3. Remover as imagens geradas localmente que podem estar corrompidas
echo "🗑️ Removendo imagens corrompidas ou geradas localmente..."
docker rmi dockerrosgemini-gemini-mcp dockerrosgemini-rosbridge 2>/dev/null || true

# 4. Limpar arquivos locais temporários (caso existam de tentativas antigas)
echo "📁 Limpando pastas temporárias locais..."
rm -rf vendor/
rm -rf gemini-cli/node_modules
rm -rf ros-mcp-server/.venv

echo "✅ Limpeza concluída!"
echo "Agora você pode copiar a nova pasta DockerRosGemini para cá e iniciar."
