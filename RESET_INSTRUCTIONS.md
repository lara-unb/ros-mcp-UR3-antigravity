# Guia de Limpeza do Ambiente (Reset) 🧹

Se você tentou instalar o projeto anteriormente e encontrou erros (build falhou, NPM não encontrado, erros de rede), **seu ambiente Docker na máquina de destino ficou com lixo residual**. 

É **obrigatório** limpar esse lixo antes de tentar a nova instalação offline, caso contrário os erros antigos persistirão.

---

## ⚠️ Sobre o uso de Internet
*   **Máquina de DESTINO (Offline):** NÃO precisa de internet para nada se você seguir os passos abaixo.
*   **Máquina de PREPARAÇÃO (Online):** O único momento que você precisa de internet é para rodar o `./scripts/prepare_offline.sh` uma única vez. Isso é necessário para "baixar as peças" que serão levadas para a máquina sem rede. **Não há como fugir disso**, pois precisamos obter os arquivos originais da nuvem para colocá-los no seu Pendrive/HD.

---

## Passo 1: Executar a Limpeza Docker (Na máquina de destino)
Se a pasta da tentativa anterior (`DockerRosGemini`) ainda estiver lá, entre nela pelo terminal e execute:

```bash
cd DockerRosGemini

# 1. Pare a infraestrutura e destrua os volumes (MUITO IMPORTANTE)
docker compose down -v

# 2. Garanta que o volume de configuração antigo foi apagado
docker volume rm dockerrosgemini_gemini-config 2>/dev/null || true

# 3. Remova as imagens locais que falharam no build anterior
docker rmi dockerrosgemini-gemini-mcp dockerrosgemini-rosbridge 2>/dev/null || true
```

## Passo 2: Excluir a Pasta Antiga
Volte um diretório e exclua completamente a pasta do projeto que falhou:

```bash
cd ..
rm -rf DockerRosGemini
```

---

## O que fazer a seguir? (O Fluxo de Sucesso)

1. **(No seu PC COM Internet):** Rode o script de preparação:
   ```bash
   ./scripts/prepare_offline.sh
   ```
   *Este script vai criar a pasta `vendor/` com tudo o que o projeto precisa.*

2. **(No seu PC COM Internet):** Copie a pasta `DockerRosGemini` inteira para um Pendrive ou HD Externo.

3. **(Na máquina SEM Internet):** Cole a pasta nova, entre nela e carregue as imagens base:
   ```bash
   cd DockerRosGemini
   docker load -i vendor/images/ubuntu_22.04.tar
   docker load -i vendor/images/ros_humble.tar
   ```

4. **(Na máquina SEM Internet):** Inicie o projeto (agora 100% local):
   ```bash
   cp .env.example .env
   # Adicione sua GEMINI_API_KEY no .env
   docker compose up --build -d
   ```
