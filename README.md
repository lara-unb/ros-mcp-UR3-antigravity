# DockerRosGemini

Este projeto integra o **Antigravity CLI** (`agy`) com o **ROS MCP Server** para controlar e monitorar robôs ROS 2, incluindo o UR3 e o URSim. Os serviços são executados em containers Docker e o build atual baixa as dependências diretamente da internet.

## Pré-requisitos

- Docker Engine instalado e em execução.
- Docker Compose v2, disponível pelo comando `docker compose`.
- Acesso à internet durante o build das imagens.
- Uma chave da API Gemini.

O host de referência é Ubuntu 22.04. O Dockerfile do Antigravity instala Python, Node.js 20 e o servidor ROS MCP; o Dockerfile do ROSbridge usa a imagem `ros:humble-ros-core` e instala o `rosbridge_suite` e o suporte ao CycloneDDS.

## Instalação e execução

Execute os comandos a partir da raiz deste repositório:

### 1. Configurar o ambiente

```bash
cp .env.example .env
```

Edite `.env` e substitua `your_api_key_here` pela sua `GEMINI_API_KEY`.

### 2. Construir e iniciar os serviços

```bash
docker compose up --build -d
```

Esse comando constrói as imagens `Dockerfile.antigravity` e `Dockerfile.rosbridge` e inicia os containers `antigravity-mcp` e `rosbridge`. O primeiro build pode demorar porque instala as dependências online. Os builds seguintes aproveitam o cache do Docker e do `uv`.

### 3. Verificar o estado dos serviços

```bash
docker compose ps
docker compose logs -f rosbridge
```

O ROSbridge publica a porta `9090` do container na porta `9090` do host. Para parar e remover os containers, mantendo o volume de configuração do Antigravity:

```bash
docker compose down
```

Para remover também o volume persistente `antigravity-config`, use `docker compose down -v`.

## Usar o Antigravity

O container `antigravity-mcp` permanece ativo em modo interativo ocioso. Execute o CLI com `agy` dentro dele:

```bash
docker exec -it antigravity-mcp agy
```

Também é possível enviar uma instrução diretamente:

```bash
docker exec -it antigravity-mcp agy "Verifique o estado do robô no URSim"
```

O entrypoint cria automaticamente `/root/.gemini/settings.json` e registra o servidor `ros-mcp-server`. A configuração é persistida no volume Docker `antigravity-config`.

## Conexão com ROSbridge e URSim

Os dois serviços participam da rede Docker `robotic-net`. De dentro da rede Compose, o hostname do ROSbridge é `rosbridge` e a porta é `9090`. Clientes executados no host acessam o serviço por `127.0.0.1:9090`, graças ao mapeamento de porta.

Ao usar as ferramentas de conexão do MCP, informe o endereço conforme o local do cliente:

- MCP ou cliente executado dentro da rede Compose: `rosbridge:9090`.
- Cliente executado no host: `127.0.0.1:9090`.

O URSim e o driver do UR3 precisam estar em execução e acessíveis pela rede do host. A configuração de cada robô fica em `ros-mcp-server/robot_specifications`; esse diretório é montado no container para permitir alterações sem reconstruir a imagem.

Para iniciar o fluxo do UR3 real, use o script incluído:

```bash
chmod +x scripts/start_robot.sh
./scripts/start_robot.sh
```

Esse script abre o driver ROS 2 em uma nova janela, inicia o Compose, conecta ao `antigravity-mcp` e encerra os serviços ao sair.

## Diagnóstico rápido

```bash
docker compose ps
docker compose logs antigravity-mcp
docker compose logs rosbridge
docker exec -it antigravity-mcp bash
```

Se a porta `9090` já estiver ocupada, altere o lado esquerdo do mapeamento `9090:9090` em `docker-compose.yml` e use a nova porta ao conectar a partir do host. A porta interna do ROSbridge continua sendo `9090`.
