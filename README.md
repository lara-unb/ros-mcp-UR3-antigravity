# DockerRosAntigravity

Este projeto integra o **Antigravity CLI** (`agy`) com o **ROS MCP Server** para controlar e monitorar robôs ROS 2, incluindo o UR3 e o URSim. O projeto base está disponível no repositório [robotmcp/ros-mcp-server](https://github.com/robotmcp/ros-mcp-server); este repositório adapta essa integração para o UR3 e o CoppeliaSim.

A infraestrutura ROS (`rosbridge` e `ros-mcp-server`) roda em containers Docker. O **Antigravity CLI (`agy`) roda diretamente no host**, fora do docker, ele se conecta ao `ros-mcp-server` por HTTP, como qualquer outro cliente de rede. Desta forma, também é possível utilizar outros agentes para comunicar com o ros-mcp-server.

## Arquitetura

```
Host (Ubuntu 22.04)
├── agy (Antigravity CLI)            ──HTTP (MCP)──►  container ros-mcp-server:9000
├── driver ur_robot_driver / URSim   ──ROS2/DDS ──►  container rosbridge:9090
└── scripts/robots/... (ex: ur3_controller.py) ──WebSocket──►  container rosbridge:9090
```

## Pré-requisitos

- Docker Engine instalado e em execução.
- Docker Compose v2, disponível pelo comando `docker compose`.
- Acesso à internet durante o build das imagens.
- (opcional)**Antigravity CLI instalado**:
  ```bash
  curl -fsSL https://antigravity.google/cli/install.sh | bash
  ```
- (opcional)Um projeto Google Cloud configurado para uso dos serviços do Antigravity, e uma conta Google autenticada no `agy` (fluxo de login do próprio CLI, executado no host).

O host de referência é Ubuntu 22.04. O Dockerfile do `ros-mcp-server` instala apenas Python e o servidor MCP; o Dockerfile do ROSbridge usa a imagem `ros:humble-ros-core` e instala o `rosbridge_suite` e o suporte ao CycloneDDS.

## Instalação e execução

Execute os comandos a partir da raiz deste repositório:

### 1. Configurar o ambiente

```bash
cp .env.example .env
```

`.env` guarda os valores locais de configuração:
- `ROS_DOMAIN_ID` — lido pelos containers via `docker-compose.yml`, deve bater
  com o `ROS_DOMAIN_ID` exportado pelo driver ROS2 nativo do host.
- `GOOGLE_CLOUD_PROJECT` — opcional, usado apenas como referência para configurar
  o `agy` no host; os containers não leem essa variável.

O arquivo `.env` está listado no `.gitignore` porque pode conter informações
sensíveis. O arquivo `.env.example` deve permanecer sem credenciais e pode ser
versionado como modelo.

### 2. Construir e iniciar os serviços de infraestrutura

```bash
docker compose up --build -d
```

Esse comando constrói as imagens `Dockerfile.ros-mcp-server` e `Dockerfile.rosbridge` e inicia os containers `ros-mcp-server` e `rosbridge`. O primeiro build pode demorar porque instala as dependências online. Os builds seguintes aproveitam o cache do Docker e do `uv`.

### 3. Verificar o estado dos serviços

```bash
docker compose ps
docker compose logs -f rosbridge
docker compose logs -f ros-mcp-server
```

Ambos os serviços ficam ativos sozinhos (`restart: unless-stopped`), sem precisar de interação manual — o `rosbridge` escuta WebSocket na porta `9090` e o `ros-mcp-server` escuta MCP via HTTP na porta `9000`.

Para parar e remover os containers:

```bash
docker compose down
```

## Configurar o Antigravity (host) para usar o `ros-mcp-server`

Como o `ros-mcp-server` expõe o transporte `streamable-http`, configure o cliente MCP do `agy` para apontar para a URL do serviço em vez de lançá-lo como subprocesso. Um exemplo de configuração está em [`ros-mcp-server/config/mcp.json`](ros-mcp-server/config/mcp.json), entrada `ros-mcp-server-http`:

```json
{
  "mcpServers": {
    "ros-mcp-server": {
      "name": "ROS-MCP Server (http)",
      "transport": "http",
      "url": "http://127.0.0.1:9000/mcp"
    }
  }
}
```

Adicione essa entrada às configurações do Antigravity CLI no host (`~/.gemini/settings.json` ou equivalente). Depois disso, basta rodar `agy` normalmente no host:

```bash
agy
# ou
agy "Verifique o estado do robô no URSim"
```

## Conexão com ROSbridge e URSim

Como `ros-mcp-server` e `rosbridge` usam `network_mode: host`, tanto os containers quanto os processos do host (`agy`, driver do UR3, scripts em `scripts/robots/`) acessam os dois serviços por `127.0.0.1`:

- ROSbridge (WebSocket): `127.0.0.1:9090`
- ros-mcp-server (MCP HTTP): `127.0.0.1:9000/mcp`

O URSim e o driver do UR3 precisam estar em execução e acessíveis pela rede do host. A configuração de cada robô fica em `ros-mcp-server/robot_specifications`; esse diretório é montado no container do `ros-mcp-server` para permitir alterações sem reconstruir a imagem.

Para iniciar o fluxo do UR3 real, use o script incluído:

```bash
chmod +x shell/start_robot.sh
./shell/start_robot.sh
```

Os scripts de operação do ambiente ficam em `shell/`. Os scripts de controle dos
robôs devem ser organizados em `scripts/robots/<robô>/<ambiente>/`, por exemplo
em `scripts/robots/ur3/real/` ou `scripts/robots/ur3/coppeliasim/`.

Esse script abre o driver ROS 2 em uma nova janela, inicia o Compose (rosbridge + ros-mcp-server) e roda o `agy` diretamente no host, encerrando os serviços Docker ao sair.

## Diagnóstico rápido

```bash
docker compose ps
docker compose logs ros-mcp-server
docker compose logs rosbridge
docker exec -it ros-mcp-server bash
```

Se a porta `9090` ou `9000` já estiver ocupada, altere o mapeamento correspondente em `docker-compose.yml`/`Dockerfile.ros-mcp-server` e ajuste a URL usada pelo `agy` no host.

## Configurar o GitHub Copilot Chat (VS Code) para usar o `ros-mcp-server`

Como o `ros-mcp-server` é um servidor MCP padrão, qualquer cliente MCP pode se conectar a ele, inclusive o agente do Copilot Chat no VS Code, seguindo a mesma arquitetura usada pelo `agy`.

1. Suba a infraestrutura normalmente (`docker compose up --build -d`), garantindo que `ros-mcp-server` esteja escutando em `http://127.0.0.1:9000/mcp`.
2. Crie (ou confira) o arquivo `.vscode/mcp.json` na raiz do repositório, apontando para o mesmo endpoint HTTP usado pelo `agy`:
   ```json
   {
     "servers": {
       "ros-mcp-server": {
         "type": "http",
         "url": "http://127.0.0.1:9000/mcp"
       }
     }
   }
   ```
3. No VS Code, abra a paleta de comandos e rode **MCP: List Servers** (ou recarregue a janela) para que o Copilot Chat detecte o servidor e carregue as ferramentas do `ros-mcp-server`.
4. Peça ao agente para conectar ao robô e explorar tópicos/serviços, do mesmo jeito que seria pedido ao `agy`:
   ```
   Conecte ao robô em 127.0.0.1 e liste os tópicos e serviços disponíveis.
   ```

Assim, o Copilot Chat passa a exercer o mesmo papel do Antigravity: cliente MCP enviando comandos ROS 2 através do `ros-mcp-server` e do `rosbridge` até o UR3 (real ou no CoppeliaSim/URSim).

## Como criar o agente customizado agy:

Crie um arquivo "ur3agent.md" no diretório .gemini/config/agents, para criar o agente globalmente. Exemplo de template de agente customizado:
```
---
name: nome-do-agente
description: Breve descrição da utilidade deste agente.
model: flash 
mainAgent: false
temperature: 0.2
tools:
  - run_command
  - read_file
  - write_file
---
# Core Instructions

Prompt Inicial (a exemplo do `prompts/EnsinaDocker.md`)

# Regras de Operação e Comportamento

1. **Formato de Resposta:** Responda de forma direta e concisa. Evite introduções longas.
2. **Restrições:** Nunca faça X. Sempre priorize Y.
3. **Escopo:** Se a solicitação do usuário estiver fora do seu escopo, avise imediatamente e não tente adivinhar.

# Protocolo de Inicialização

Ao iniciar esta sessão, siga EXATAMENTE estes passos de forma silenciosa:
1. Execute `pwd` para identificar a raiz do projeto.
2. Leia o arquivo X (se aplicável ao contexto) para entender o estado inicial.
3. Apresente um painel de status curto confirmando que você carregou o ambiente com sucesso e está pronto.
4. Outras instruções de BOOT.
```


Neste projeto, `prompts/ur3agent.md` é o agente customizado utilizado.
Para iniciar, utilize o CLI:

```bash
agy --agent ur3-lab-agent
```

Perceba que no CLI, é utilizado o "name: " da descrição do agente, não o nome do arquivo "ur3agent.md".
Para mais informações, visite o site de [Subagentes](https://antigravity.google/docs/cli/subagents/).

## Como descobrir o IP do computador para colocar no External Control do UR3:

```bash
ip route get $(ip route | awk '/default/ {print $3}' | head -n1) | grep -oP 'src \K\S+'
```

ou

```bash
hostname -I
```

## Como descobrir o IP do UR3?
```bash
ip neigh
```

```bash
for ip in $(ip -4 neigh | awk '{print $1}'); do timeout 1 bash -c "</dev/tcp/$ip/30002" 2>/dev/null && echo "O IP do UR3 é: $ip"; done
```
## Resumo do teste de integração (Copilot Chat ↔ ros-mcp-server)

Teste realizado sem UR3/driver instalado, apenas para validar a comunicação MCP:

1. **Bug encontrado e corrigido:** `ros-mcp-server/pyproject.toml` tinha `fastmcp>=2.11.3` sem teto de versão. O `uv pip install` resolvia para o `fastmcp 4.0.3`, que removeu o módulo `fastmcp.tools.tool.ToolResult` usado em `ros_mcp/tools/topics.py`, deixando o container em restart-loop (`ModuleNotFoundError`). Corrigido para `fastmcp>=2.11.3,<3` (linha 2.x é a API compatível com o código atual).
2. **`docker compose up --build -d`** subiu `rosbridge` (porta 9090) e, após o fix, `ros-mcp-server` (porta 9000) normalmente.
3. **Validação via Copilot Chat como cliente MCP** (usando `.vscode/mcp.json` apontando para `http://127.0.0.1:9000/mcp`):
   - `connect_to_robot(127.0.0.1:9090)` → porta aberta (o "ping" falha por falta do binário `ping` no container, sem relação com a conexão real).
   - `get_topics()` → retornou apenas os tópicos internos do ROS2/rosbridge (`/rosout`, `/parameter_events`, `/client_count`, `/connected_clients`), o esperado sem robô conectado.
   - `get_nodes()` → retornou `/rosapi`, `/rosapi_params`, `/rosbridge_websocket`.
4. **Conclusão:** o pipeline Copilot Chat → `ros-mcp-server` → `rosbridge` → ROS2 está funcional. Falta apenas conectar o driver do UR3/URSim para ver tópicos/nós do robô.

**Pendências para revisão no laboratório:**
- Commitar o fix do `pyproject.toml` (ainda estava só no working tree no momento do teste).
- Decidir se o `.vscode/mcp.json` deve ser versionado no repositório.
- Repetir o teste de `connect_to_robot`/`get_topics` com o driver do UR3 (ou URSim/CoppeliaSim) ativo para confirmar que os tópicos do robô aparecem.