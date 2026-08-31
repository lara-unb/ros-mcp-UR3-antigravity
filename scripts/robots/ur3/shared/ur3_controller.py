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
            {"a": 0.0,      "d": 0.1519,  "alpha": math.pi/2},
            {"a": -0.24365, "d": 0.0,     "alpha": 0.0},
            {"a": -0.21325, "d": 0.0,     "alpha": 0.0},
            {"a": 0.0,      "d": 0.11235, "alpha": math.pi/2},
            {"a": 0.0,      "d": 0.08535, "alpha": -math.pi/2},
            {"a": 0.0,      "d": 0.0819,  "alpha": 0.0}
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
        try:
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
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if self.connected:
                print(f"[AVISO] Telemetria encerrada: {e}")

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
            await asyncio.sleep(0.05)
        return list(self.current_joints)

    def dh_matrix(self, theta, a, d, alpha):
        """Calcula a matriz de transformação homogênea padrão D-H."""
        ct = math.cos(theta)
        st = math.sin(theta)
        ca = math.cos(alpha)
        sa = math.sin(alpha)
        return np.array([
            [ct, -st * ca,  st * sa, a * ct],
            [st,  ct * ca, -ct * sa, a * st],
            [0.0, sa,      ca,      d],
            [0.0, 0.0,     0.0,     1.0]
        ], dtype=float)

    def forward_kinematics(self, q):
        """Calcula a Cinemática Direta a partir das juntas dadas."""
        T = np.eye(4, dtype=float)
        transforms = [T]
        for i in range(6):
            Ti = self.dh_matrix(q[i], self.dh_params[i]["a"], self.dh_params[i]["d"], self.dh_params[i]["alpha"])
            T = T @ Ti
            transforms.append(T)
        return transforms

    def compute_jacobian(self, q):
        """Calcula a Matriz Jacobiana Geométrica (6x6) baseada nos parâmetros D-H."""
        transforms = self.forward_kinematics(q)
        p_e = transforms[-1][:3, 3]
        J = np.zeros((6, 6), dtype=float)
        for i in range(6):
            T_i = transforms[i]
            z_i = T_i[:3, 2]
            p_i = T_i[:3, 3]
            J[:3, i] = np.cross(z_i, p_e - p_i)
            J[3:, i] = z_i
        return J

    def _orientation_error(self, R_curr, R_d):
        """Calcula o erro de orientação angular entre rotações atuais e desejadas."""
        R_err = R_d @ R_curr.T
        return 0.5 * np.array([
            R_err[2, 1] - R_err[1, 2],
            R_err[0, 2] - R_err[2, 0],
            R_err[1, 0] - R_err[0, 1]
        ], dtype=float)

    def inverse_kinematics(self, target_pos, target_rot=None, q_init=None, max_iter=100, tol=1e-4, damping=0.01):
        """Resolve a Cinemática Inversa usando Damped Least Squares (Jacobiana)."""
        if q_init is None:
            if self.current_joints is not None:
                q = np.array(self.current_joints, dtype=float)
            else:
                q = np.array([0.0, -math.pi/2, 0.0, -math.pi/2, 0.0, 0.0], dtype=float)
        else:
            q = np.array(q_init, dtype=float)

        target_pos = np.array(target_pos, dtype=float)
        if target_rot is None:
            target_rot = self.forward_kinematics(q)[-1][:3, :3]

        for _ in range(max_iter):
            transforms = self.forward_kinematics(q)
            p_curr = transforms[-1][:3, 3]
            R_curr = transforms[-1][:3, :3]
            
            e_p = target_pos - p_curr
            e_o = self._orientation_error(R_curr, target_rot)
            e = np.hstack([e_p, e_o])
            
            if np.linalg.norm(e) < tol:
                return q.tolist(), True
                
            J = self.compute_jacobian(q)
            J_dls = J.T @ np.linalg.inv(J @ J.T + (damping ** 2) * np.eye(6))
            dq = J_dls @ e
            
            step = np.linalg.norm(dq)
            if step > 0.2:
                dq = dq * (0.2 / step)
            q = q + dq
            
        return q.tolist(), False

    def generate_cycloidal_trajectory(self, q_start, q_end, hz=20):
        """Regra 3: Geração de curva S (Cicloidal) entre duas configurações articulares."""
        q_start = np.array(q_start, dtype=float)
        q_end = np.array(q_end, dtype=float)
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

    def generate_cartesian_circle_trajectory(self, center=None, radius=0.06, plane="xz", hz=20, duration=None):
        """Gera trajetória cartesiana para círculo perfeito interpolada com S-Curve e resolvida via Cinemática Inversa D-H."""
        if center is None:
            center = np.array([0.0, -0.25, 0.35], dtype=float)
        else:
            center = np.array(center, dtype=float)

        q_ref = np.array([0.0, -math.pi/2, 0.0, -math.pi/2, 0.0, 0.0], dtype=float)
        R_ref = self.forward_kinematics(q_ref)[-1][:3, :3]

        # Determinar orientação e equação do plano
        def get_circle_point(angle):
            if plane.lower() == "xz":
                return center + np.array([radius * math.cos(angle), 0.0, radius * math.sin(angle)])
            elif plane.lower() == "xy":
                return center + np.array([radius * math.cos(angle), radius * math.sin(angle), 0.0])
            elif plane.lower() == "yz":
                return center + np.array([0.0, radius * math.cos(angle), radius * math.sin(angle)])
            else:
                raise ValueError(f"Plano inválido: {plane}")

        # Estimar duração para garantir velocidade articular < 0.15 rad/s
        nominal_duration = 35.0 if duration is None else duration
        steps = int(nominal_duration * hz)
        
        # Obter ponto de início (ângulo 0)
        p_start = get_circle_point(0.0)
        q_start, ok = self.inverse_kinematics(p_start, R_ref, q_ref)
        if not ok:
            raise RuntimeError("Falha ao calcular IK para o ponto inicial do círculo.")

        # Gerar pontos ao longo da curva S cicloidal
        q_traj = []
        q_curr = list(q_start)
        
        times = np.linspace(0.0, nominal_duration, steps + 1)
        for t in times:
            tau = t / nominal_duration
            s = tau - (1.0 / (2.0 * math.pi)) * math.sin(2.0 * math.pi * tau)
            angle = 2.0 * math.pi * s
            p_t = get_circle_point(angle)
            q_sol, ok = self.inverse_kinematics(p_t, R_ref, q_curr)
            if not ok:
                raise RuntimeError(f"Cinemática Inversa não convergiu no ponto {p_t}")
            q_curr = q_sol
            q_traj.append(q_sol)

        q_traj = np.array(q_traj)
        dt = 1.0 / hz
        v_traj = np.gradient(q_traj, dt, axis=0)
        a_traj = np.gradient(v_traj, dt, axis=0)

        # Ajuste de escala de tempo caso a velocidade máxima exceda o limite seguro
        max_vel = np.max(np.abs(v_traj))
        if max_vel > self.MAX_VELOCITY:
            scale_factor = (max_vel / self.MAX_VELOCITY) * 1.1
            actual_duration = nominal_duration * scale_factor
            return self.generate_cartesian_circle_trajectory(center, radius, plane, hz, duration=actual_duration)

        # Formatar pontos para mensagem ROS 2
        trajectory_points = []
        for i in range(len(times)):
            tau = times[i]
            point = {
                "positions": q_traj[i].tolist(),
                "velocities": v_traj[i].tolist(),
                "accelerations": a_traj[i].tolist(),
                "time_from_start": {"sec": int(tau), "nanosec": int((tau - int(tau)) * 1e9)}
            }
            trajectory_points.append(point)

        return trajectory_points, q_start

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

if __name__ == "__main__":
    async def main():
        agent = UR3AutonomousController()
        await agent.connect()
        await asyncio.sleep(1.0)
        await agent.move_to_home()
        await asyncio.sleep(1.0)
        if agent.ws:
            await agent.ws.close()
            
    asyncio.run(main())
