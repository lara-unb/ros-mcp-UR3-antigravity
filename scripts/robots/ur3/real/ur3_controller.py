import asyncio
import websockets
import json
import time
import math
import numpy as np

class UR3AutonomousController:
    def __init__(self, uri="ws://localhost:9090"):
        self.uri = uri
        self.ws = None
        self.current_joints = None
        self.last_physical_msg_time = 0
        self.connected = False
        
        # Parâmetros de Denavit-Hartenberg (D-H) estritos do UR3
        self.dh_params = [
            {'a': 0.0,      'd': 0.1519,  'alpha': math.pi/2},
            {'a': -0.24365, 'd': 0.0,     'alpha': 0.0},
            {'a': -0.21325, 'd': 0.0,     'alpha': 0.0},
            {'a': 0.0,      'd': 0.11235, 'alpha': math.pi/2},
            {'a': 0.0,      'd': 0.08535, 'alpha': -math.pi/2},
            {'a': 0.0,      'd': 0.0819,  'alpha': 0.0}
        ]
        
        self.joint_names = [
            "shoulder_pan_joint", "shoulder_lift_joint", "elbow_joint", 
            "wrist_1_joint", "wrist_2_joint", "wrist_3_joint"
        ]
        
        self.MAX_VELOCITY = 0.15  # rad/s

    async def connect(self):
        """Estabelece conexão com o rosbridge_server e configura os tópicos."""
        try:
            self.ws = await websockets.connect(self.uri)
            print("[INFO] Conectado ao rosbridge_server.")
            
            # Regra 1: Advertise apenas uma vez na inicialização
            adv_msg = {
                "op": "advertise",
                "topic": "/scaled_joint_trajectory_controller/joint_trajectory",
                "type": "trajectory_msgs/msg/JointTrajectory"
            }
            await self.ws.send(json.dumps(adv_msg))
            await asyncio.sleep(0.5)  # Atraso obrigatório para processamento interno
            
            # Iniciar subscrição de telemetria
            sub_msg = {
                "op": "subscribe",
                "topic": "/joint_states",
                "type": "sensor_msgs/msg/JointState"
            }
            await self.ws.send(json.dumps(sub_msg))
            
            self.connected = True
            asyncio.create_task(self.listen_telemetry())
            asyncio.create_task(self.connection_watchdog())
            
        except Exception as e:
            print(f"[ERRO] Falha na conexão WebSocket: {e}")

    async def listen_telemetry(self):
        """Processa as mensagens WebSocket do rosbridge."""
        async for msg_str in self.ws:
            msg = json.loads(msg_str)
            if msg.get("op") == "publish" and msg.get("topic") == "/joint_states":
                data = msg.get("msg", {})
                header = data.get("header", {})
                stamp = header.get("stamp", {})
                sec = stamp.get("sec", 0)
                
                # Regra 5: Filtrar apenas dados do robô físico (Unix Epoch)
                if sec > 1000000000:
                    incoming_names = data.get("name", [])
                    incoming_pos = data.get("position", [])
                    
                    if len(incoming_names) == len(self.joint_names):
                        # Reordenar posições para o formato padrão do D-H
                        ordered_pos = [0.0] * 6
                        for i, name in enumerate(self.joint_names):
                            if name in incoming_names:
                                idx = incoming_names.index(name)
                                ordered_pos[i] = incoming_pos[idx]
                        
                        self.current_joints = ordered_pos
                        self.last_physical_msg_time = time.time()
                    # A gravação de logs (telemetria) pode ser expandida aqui

    async def connection_watchdog(self):
        """Regra 5: Monitora a conexão física. Se cair por 5s, aborta."""
        while self.connected:
            await asyncio.sleep(1)
            if self.last_physical_msg_time > 0:
                elapsed = time.time() - self.last_physical_msg_time
                if elapsed > 5.0:
                    print("[ALERTA CRÍTICO] Falha na telemetria. Nenhuma mensagem Unix timestamp detectada em 5s.")
                    print("[ALERTA CRÍTICO] Abortando execução imediatamente por segurança de hardware.")
                    self.connected = False
                    if self.ws:
                        await self.ws.close()
                    break

    async def fetch_current_state(self):
        """Regra 4: Aguarda leitura exata do robô físico. Nunca usa posições teóricas."""
        start_time = time.time()
        while self.current_joints is None or (time.time() - self.last_physical_msg_time > 1.0):
            if time.time() - start_time > 2.0:
                raise RuntimeError("Falha ao obter estado atual do robô em 2 segundos. Cálculo de trajetória abortado.")
            await asyncio.sleep(0.1)
        return self.current_joints

    def generate_cycloidal_trajectory(self, q_start, q_end, hz=20):
        """Regra 3: Geração de curva S (Cicloidal) entre dois pontos nas juntas."""
        q_start = np.array(q_start)
        q_end = np.array(q_end)
        delta_q = q_end - q_start
        
        # Calcular tempo necessário baseado na velocidade máxima permitida (0.15 rad/s)
        max_delta = np.max(np.abs(delta_q))
        duration = max(2.0, (2 * max_delta) / self.MAX_VELOCITY)
        
        steps = int(duration * hz)
        trajectory = []
        
        for i in range(steps + 1):
            t = i / steps
            tau = t * duration
            
            # Equação da Curva Cicloidal
            s = t - (1 / (2 * math.pi)) * math.sin(2 * math.pi * t)
            ds_dt = (1 - math.cos(2 * math.pi * t)) / duration
            dds_dt = (2 * math.pi * math.sin(2 * math.pi * t)) / (duration**2)
            
            pos = q_start + delta_q * s
            vel = delta_q * ds_dt
            acc = delta_q * dds_dt
            
            point = {
                "positions": pos.tolist(),
                "velocities": vel.tolist(),
                "accelerations": acc.tolist(),
                "time_from_start": {"sec": int(tau), "nanosec": int((tau - int(tau)) * 1e9)}
            }
            trajectory.append(point)
            
        return trajectory

    async def publish_trajectory(self, trajectory_points):
        """Publica a trajetória no rosbridge_server instantaneamente."""
        if not self.connected:
            print("[ERRO] Não conectado, impossível publicar.")
            return

        # Regra 2: Timestamp forçado a zero para evitar dessincronização simulação/real
        traj_msg = {
            "op": "publish",
            "topic": "/scaled_joint_trajectory_controller/joint_trajectory",
            "msg": {
                "header": {
                    "stamp": {"sec": 0, "nanosec": 0}
                },
                "joint_names": self.joint_names,
                "points": trajectory_points
            }
        }
        await self.ws.send(json.dumps(traj_msg))
        print(f"[INFO] Trajetória publicada com {len(trajectory_points)} pontos.")

    async def move_to_home(self):
        """Regra 4: Retorna para pose Home Cartesiano de forma segura."""
        print("[INFO] Iniciando sequência para Home Cartesiano...")
        try:
            current = await self.fetch_current_state()
            target_home = [0.0, -1.5708, 0.0, -1.5708, 0.0, 0.0]
            
            print("[INFO] Posição atual obtida. Gerando trajetória cicloidal (S-Curve)...")
            traj_points = self.generate_cycloidal_trajectory(current, target_home)
            
            await self.publish_trajectory(traj_points)
        except Exception as e:
            print(f"[ERRO CRÍTICO] {e}")

    # TODO: Implementação da Cinemática Inversa via Jacobiana baseada em self.dh_params
    def inverse_kinematics(self, target_pose):
        pass

if __name__ == "__main__":
    async def main():
        agent = UR3AutonomousController()
        await agent.connect()
        # Exemplo de operação inicial segura
        # await agent.move_to_home()
        
    # Descomentar para execução real
    # asyncio.run(main())
