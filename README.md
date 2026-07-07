# DockerRosGemini 🤖🧠

Este projeto integra o **Gemini CLI** com um **ROS MCP Server**, permitindo o controle e monitoramento de robôs ROS utilizando modelos de linguagem Gemini. Esta versão foi otimizada para ser **totalmente autocontida (offline)** e para se comunicar com simuladores (como o **URSim**) rodando diretamente no host Ubuntu 22.04.

## Estrutura do Projeto

- `gemini-cli/`: Interface de linha de comando baseada em Node.js.
- `ros-mcp-server/`: Servidor MCP em Python para ponte com ROS.
- `vendor/`: (Gerado) Cache offline de imagens Docker, pacotes NPM e Python Wheels.
- `scripts/`: Scripts de preparação offline e entrypoint de configuração automática.
- `Dockerfile.gemini`: Ambiente isolado com configuração dinâmica via entrypoint.
- `Dockerfile.rosbridge`: Container dedicado para a ponte ROS2.

## 🚀 Como Rodar (Modo Offline)

Siga estes passos para garantir que o projeto funcione sem internet na máquina de destino.

### 1. Preparação (Em uma máquina COM internet)
Execute o script de preparação para baixar todas as dependências:
```bash
chmod +x scripts/prepare_offline.sh
./scripts/prepare_offline.sh
```
Isso criará a pasta `vendor/` com as imagens Docker (`.tar`), pacotes NPM (`.tgz`) e Python Wheels necessários.

### 2. Transferência
Mova a pasta completa do projeto `DockerRosGemini` para a máquina de destino (Ubuntu 22.04).

### 3. Instalação e Execução (Na máquina SEM internet)
Dentro da pasta do projeto na máquina de destino:

#### Carregar Imagens Base:
```bash
docker load -i vendor/images/ubuntu_22.04.tar
docker load -i vendor/images/ros_humble.tar
```

#### Configurar Variáveis de Ambiente:
```bash
cp .env.example .env
# Edite o .env e adicione sua GEMINI_API_KEY
```

#### Build e Execução:
```bash
docker compose up --build -d
```
*O build utilizará apenas os arquivos locais da pasta `vendor/`.*

## 🛠️ Como Utilizar e Integração com URSim

### Comunicação com URSim
O projeto utiliza `network_mode: host`. Isso significa que o container e o URSim (instalado no seu Ubuntu) compartilham a mesma rede.
- O `rosbridge` escuta na porta **9090** do host.
- O `ros-mcp-server` conecta-se ao URSim via `localhost:9090`.

### Interagindo com o Gemini
O container principal (`gemini-mcp`) fica rodando em segundo plano. Você pode chamá-lo diretamente:

```bash
# Executar um comando direto
docker exec -it gemini-mcp gemini "Verifique o estado do robô no URSim"

# Entrar no terminal interativo do container
docker exec -it gemini-mcp /bin/bash
```

## Notas Técnicas
- **Configuração Automática:** O arquivo `settings.json` do Gemini é gerado automaticamente no primeiro boot pelo `entrypoint.sh`, evitando problemas com volumes Docker vazios.
- **DDS:** Utiliza-se o CycloneDDS (`rmw_cyclonedds_cpp`) para garantir estabilidade na comunicação via rede host.
