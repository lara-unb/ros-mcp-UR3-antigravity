# Guia Definitivo do Gêmeo Digital: UR3 (ROS2 + URSim + CoppeliaSim)

**ATENÇÃO, NOVA INSTÂNCIA DA IA:** Este documento contém o histórico exaustivo, as regras inegociáveis e a arquitetura completa para operar o Gêmeo Digital do braço robótico UR3. Leia-o atentamente e não tente criar "atalhos" lógicos. O objetivo primário deste ambiente é que o robô virtual no CoppeliaSim se comporte **exatamente** com as mesmas restrições de tempo, física e comunicação do controlador industrial real do Universal Robots. Atalhos de software destroem a validade da simulação.

---

## 1. Filosofia e Objetivo Primário
O objetivo do projeto é validar trajetórias e lógicas de controle de forma que a simulação no CoppeliaSim não seja apenas um "desenho animado", mas uma verdadeira simulação mecânica regida pelo controlador ROS2. 
- **Sem teletransporte:** O robô virtual deve acelerar, viajar e parar respeitando a inércia e o clock de tempo real, sem pular direto para posições alvo.
- **Tolerância Zero para Atrasos:** A simulação virtual não pode rodar mais rápida ou mais devagar que o tempo real (clock wall-time). Um movimento de 3 segundos no ROS deve demorar exatos 3 segundos no CoppeliaSim.

## 2. Arquitetura de Rede, Tópicos e Conexões
- **Topologia:** O ROS2 é o mestre. O URSim (simulador oficial da UR que roda o software real da caixa de controle) atua como o driver industrial. O CoppeliaSim é apenas um espelho físico passivo.
- **Tópico Oficial:** O envio de movimentos é sempre feito através do tópico padrão do ROS2 para manipuladores UR: ` /scaled_joint_trajectory_controller/joint_trajectory ` (tipo `trajectory_msgs/msg/JointTrajectory`).
- **Conexão CoppeliaSim (simROS2):** O CoppeliaSim não deve ser controlado por portas Socket TCP personalizadas em LUA. Ele utiliza o plugin oficial `simROS2`, que o torna um nó legítimo na rede DDS do ROS2. O script Child em LUA do braço invoca `simROS2.createSubscription` para ouvir o tópico do ROS passivamente.
- **Conexão Externa (Rosbridge 9090):** Caso aplicações web ou telemetrias de front-end entrem no fluxo de trabalho do usuário, a porta `9090` via WebSockets (pacote `rosbridge_server`) é utilizada como a ponte de dados. Não desabilite ou bloqueie o rosbridge.

## 3. O Nó C++ Publisher e a Restrição do Buffer (CRÍTICO)
Para enviar trajetórias perfeitas do C++ para o URSim, algumas restrições industriais devem ser simuladas e respeitadas no código ROS2:
- **"One-Shot" Publish:** NUNCA publique trajetórias repetidamente dentro de um `Timer` contínuo. Mandar o mesmo objetivo repetidamente faz o controlador PID do URSim resetar o cálculo interno, engasgando fisicamente as juntas. Publique a mensagem de 60 pontos e em seguida aplique `timer_->cancel()`.
- **O "Delay" de Buffer Inicial (500ms):** O URSim precisa de tempo para ingerir e processar os pontos matemáticos antes que o relógio comece a contar a execução. Portanto, ao construir o cabeçalho da mensagem no C++, adicione um "atraso" intencional no tempo futuro: `msg.header.stamp = current_time + rclcpp::Duration(0, 500000000);`. Sem esses 500ms, o controlador tentará alcançar um ponto no passado e pulará posições agressivamente.

## 4. Configuração do CoppeliaSim (Script LUA)
Para garantir o comportamento industrial no simulador, o script LUA deve ser configurado cirurgicamente na função `sysCall_init`:
- **Forçar Tempo Real (Real-time Mode):** Desative o processamento assíncrono acelerado. A física deve correr sincronizada ao relógio do ROS.
  `sim.setBoolParam(sim.boolparam_realtime_simulation, true)`
- **Calculation Passes cravado em 1:** Evite "time dilation" forçando a engine a calcular as inércias apenas 1 vez por tick.
  `sim.setInt32Param(sim.intparam_dynamic_step_divider, 1)`
- **Blindagem de Inércia e PID (Rigidez Industrial):** Por padrão, os motores no CoppeliaSim são esponjosos. Para evitar que a gravidade arraste o braço e destrua a trajetória espacial de 3 segundos, injete força industrial nos motores virtuais para que eles acompanhem a matemática perfeitamente:
  `sim.setJointForce(jointHandles[i], 5000.0)`
  `pcall(function() sim.setObjectFloatParam(jointHandles[i], sim.jointfloatparam_pid_p, 100.0) end)`
- **O "Ponto Zero" (Interpolação):** Quando o nó C++ enviar um movimento com apenas 1 ponto final, o LUA precisa criar o ponto de início lendo a pose atual (`sim.getJointPosition`) no exato momento da recepção do comando ROS. Sem isso, a matemática falha ao tentar interpolar tempo/espaço.

## 5. Telemetria: A Caixa-Preta em formato CSV
O objetivo da prova de conceito é empírico. Precisamos gravar logs (CSVs) das 6 juntas de ambos os sistemas e cruzar os dados.
- **O que gravar:** O formato deve ser: `timestamp, source, shoulder_pan, shoulder_lift, elbow, wrist_1, wrist_2, wrist_3`.
- **Como extrair no ROS2 (Python Logger):** Assine o tópico `/joint_states`. Use OBRIGATORIAMENTE o timestamp da mensagem (`msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9`) e nunca o `time.time()` do sistema operacional, para garantir pureza do dado.
- **Como extrair no CoppeliaSim (LUA):** O próprio script atrelado ao robô deve abrir o arquivo `.csv` na raiz do Linux via `io.open`. Dentro do loop dinâmico `sysCall_sensing()`, extraia `sim.getSimulationTime()` e os radianos em tempo real. Feche o arquivo em `sysCall_cleanup()`.

## 6. Validação Visual e Offset de Cinemática (CRÍTICO)
O veredito final do Gêmeo Digital exige plotar as coordenadas espaciais (X, Y, Z) do TCP da ferramenta para provar que a curva real (URSim) foi igual à curva virtual (Coppelia). 
- **Cinemática Direta (Forward Kinematics):** O script `plot_tcp_trajectory.py` (usando Matplotlib) lê os CSVs e processa os dados nas matrizes padrão Denavit-Hartenberg (DH) do UR3.
- **O Offset de Matriz:** A orientação "Home" de Zero Graus das juntas do CoppeliaSim NÃO É a mesma estabelecida pelo padrão industrial UR/ROS2. Ao processar os dados vindos do CSV do CoppeliaSim, **é mandatório subtrair -90 graus (-pi/2) das juntas `shoulder_lift` e `wrist_1`**. Caso a nova instância esqueça o offset, as trajetórias 3D se despedaçarão e o gráfico parecerá quebrado.
- **Bounding Box Isométrica (Aspect Ratio):** Nunca utilize o auto-scaling do eixo Y do Matplotlib. O zoom automático destrói a visualização transformando desvios inofensivos de `0.0001` radianos em desvios absurdos na tela. O gráfico deve criar forçosamente uma "caixa" 3D isométrica perfeita, em que `xlim`, `ylim` e `zlim` tenham rigorosamente a mesma medida (Aspect Ratio 1:1:1).

Ao final de todas essas configurações matemáticas, a linha tracejada do mundo virtual no Matplotlib sobreporá milimetricamente a linha sólida do mundo industrial, validando com sucesso o ambiente do Gêmeo Digital para qualquer futuro experimento, e sem usar qualquer atalho no percurso.
