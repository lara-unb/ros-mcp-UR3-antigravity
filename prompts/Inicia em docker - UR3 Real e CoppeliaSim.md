### 📋 Prompt de Transferência de Contexto (Copie e Cole para a nova instância):

Olá! Nós estamos controlando um braço robótico UR3 físico e uma simulação no CoppeliaSim simultaneamente via ROS2. Para que você não perca tempo investigando, aqui estão as regras de arquitetura e os desafios de segurança que já superamos. Siga essas diretrizes estritamente em todos os seus scripts:

**1. Arquitetura de Rede (O Contêiner Isolado):**
Você está rodando dentro de um contêiner Docker isolado (`antigravity-mcp`) sem acesso a comandos nativos do ROS2 (`rclpy`, `colcon`). O ROS2 está exposto no host via **`rosbridge_server`**. 
*Regra:* TODOS os seus scripts devem ser feitos em **Python puro**, usando a biblioteca `websockets`. Conecte-se em `ws://localhost:9090`. Para mover o robô, você deve publicar no tópico `/scaled_joint_trajectory_controller/joint_trajectory` seguindo o fluxo obrigatório do rosbridge: `"op": "advertise"`, aguardar 0.5s, enviar `"op": "publish"`, aguardar 1.0s, e enviar `"op": "unadvertise"`.

**2. O Conflito de Hardware e a Regra do "Relógio ZERO":**
Inicialmente o robô simulado se movia, mas o físico descartava silenciosamente as nossas trajetórias. Descobrimos que isso ocorria por conflito de relógios de hardware (Unix Epoch da placa-mãe do UR3) com os relógios de software na rede ROS2.
*Regra:* O campo de timestamp no cabeçalho das mensagens publicadas deve SEMPRE ser forçado a **ZERO**. 
Envie exatamente assim na raiz da mensagem JSON: `"header": { "stamp": { "sec": 0, "nanosec": 0 } }`. Isso é um bypass no ROS2 chamado "Execução Imediata", forçando a controladora de metal a assumir o seu próprio tempo interno, sincronizando a simulação e o hardware instantaneamente.

**3. Segurança e o Modo 'Reduced':**
O hardware físico do UR3 está operando sob regras rígidas do Modo 'Reduced'. Ele abortará e travará se você enviar movimentos bruscos.
*Regra:* Nunca use tempos fixos (ex: 5 segundos) de forma arbitrária. Calcule o tempo dinamicamente usando uma velocidade super segura de no máximo `0.15 rad/s`. Nunca use interpolação linear. Todo movimento deve ser calculado por você usando **S-Curve (Curva Cicloidal)**, gerando pontos em alta resolução (ex: 20 Hz) para posições e velocidades, garantindo que a trajetória inicie e termine em aceleração zero. O usuário deve manter o slider de velocidade do robô real (Teach Pendant) em 100%.

**4. Desenhos Cartesianos via Cinemática Inversa Numérica:**
Para realizar tarefas de precisão em parede (como desenhar as formas 'L', Círculos e 'S' que já fizemos), nós não usamos planejadores externos.
*Regra:* Utilizamos funções nativas no script Python de Cinemática Direta (Parâmetros D-H do UR3) e um Solucionador de Cinemática Inversa (IK Solver numérico via Matriz Jacobiana e Pseudo-inversa). A posição "Home Segura" de partida é sempre `[0.0, -1.5708, 0.0, -1.5708, 0.0, 0.0]`. Travamos a rotação da garra na matriz original do Home e variamos apenas as posições (X,Y,Z).

**5. Telemetria e Coleta de Dados (CSVs Separados):**
Nós coletamos CSVs do movimento para análise de latência e erro. A gravação NÃO mistura os dados.
*Regra:* O script Lua rodando dentro do CoppeliaSim já gera e salva o CSV da simulação diretamente na máquina host do usuário. O seu papel (como script Python dentro do container ouvindo `/joint_states`) é gravar **APENAS** os dados do robô real. Para isso, o script Python usa um `if sec > 1000000000` (Unix Epoch) para ignorar os relógios do simulador (que começam do zero) e salvar o CSV do robô físico de forma perfeitamente isolada no diretório `/app`.
