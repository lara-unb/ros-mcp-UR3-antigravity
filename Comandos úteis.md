# Iniciar docker com  URSim
ros2 run ur_client_library start_ursim.sh -m ur3 -i 192.168.56.101

# Após iniciar com robô "Normal" no URSim:
source /opt/ros/humble/setup.bash 
ros2 launch ur_robot_driver ur_control.launch.py \
  ur_type:=ur3 \
  robot_ip:=192.168.56.101 \
  launch_rviz:=true

# Em caso de exit code -6 por timeout:
ros2 launch ur_robot_driver ur_control.launch.py \
  ur_type:=ur3 \
  robot_ip:=192.168.56.101 \
  launch_rviz:=true \
  reverse_ip:=192.168.56.1

# Iniciar driver para conectar com UR3 real (conferir IP):
ros2 launch ur_robot_driver ur_control.launch.py \
      ur_type:=ur3 \
      robot_ip:=192.168.1.102 \
      launch_rviz:=true

# Como instalar o Antigravity:
curl -fsSL https://antigravity.google/cli/install.sh | bash

# Montar docker no diretório DockerRosAgy:
docker load -i vendor/images/ubuntu_22.04.tar
docker load -i vendor/images/ros_humble.tar

# Criar docker:
docker compose up --build -d

# Ativar o docker (up):
docker start antigravity-mcp

# Executar docker e abrir o Antigravity:
docker exec -it antigravity-mcp agy

ou

docker exec -it antigravity-mcp bash
agy

# Listar todos os dockers:
docker ps -a

# Excluir um docker:
docker rm <CONTAINER_ID_OU_NOME>

# Excluir um docker que está em execução:
docker rm -f <CONTAINER_ID_OU_NOME>

# Faxina em massa dos dockers parados (usar com muito cuidado):
docker container prune
