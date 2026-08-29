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
