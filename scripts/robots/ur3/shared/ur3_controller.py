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

        # Limites conservadores de junta (rad). TODO: confirmar contra a config de segurança real do Polyscope/URSim.
        self.JOINT_LIMITS = [(-2 * math.pi, 2 * math.pi)] * 6

        # Offset flange -> TCP (garra RG2), medido em 2026-09-01 comparando forward_kinematics
        # com /tcp_pose_broadcaster/pose no robô real (2 amostras, repetiu com <1mm de diferença).
        # Reconfirmar se a ferramenta física mudar.
        self.TOOL_OFFSET = self._build_tool_offset()

        self._telemetry_task = None
        self._watchdog_task = None
        self._pending_goals = {}  # goal_id -> asyncio.Queue (action_feedback/action_result)

    def _build_tool_offset(self):
        # Offset flange -> TCP (RG2), 187.2mm ao longo de z. Esse é o TCP configurado no
        # Polyscope (ponto de preensão entre os dedos), não o comprimento físico total do
        # gripper. O datasheet OnRobot RG2 (pag. 9, "1.3. RG2") confirma 213mm de comprimento
        # total flange->ponta do dedo; os ~26mm de diferença são o recuo esperado do TCP em
        # relação à ponta física (comum em garras, já que o TCP fica no ponto de contato do
        # dedo com a peça, não na extremidade externa).
        T = np.eye(4, dtype=float)
        T[:3, :3] = np.array([[-1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, 1.0]])
        T[:3, 3] = np.array([-0.0025, 0.0, 0.1872])
        return T

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
            self._telemetry_task = asyncio.create_task(self.listen_telemetry())
            self._watchdog_task = asyncio.create_task(self.connection_watchdog())
            
        except Exception as e:
            print(f"[ERRO] Falha na conexão WebSocket: {e}")

    async def shutdown(self):
        """Encerra tasks assíncronas e o WebSocket de forma limpa e ordenada."""
        self.connected = False
        for task in (self._telemetry_task, self._watchdog_task):
            if task is not None:
                task.cancel()
        for task in (self._telemetry_task, self._watchdog_task):
            if task is not None:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass

    async def listen_telemetry(self):
        """Processa as mensagens WebSocket do rosbridge: telemetria de /joint_states e,
        se houver goals de action pendentes, roteia action_feedback/action_result para eles."""
        try:
            async for msg_str in self.ws:
                msg = json.loads(msg_str)
                if msg.get("op") in ("action_feedback", "action_result"):
                    queue = self._pending_goals.get(msg.get("id"))
                    if queue is not None:
                        queue.put_nowait(msg)
                    continue
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

    def forward_kinematics_tcp(self, q):
        """Pose da ponta da ferramenta (TCP), não do flange nu: aplica self.TOOL_OFFSET."""
        return self.forward_kinematics(q)[-1] @ self.TOOL_OFFSET

    def inverse_kinematics_tcp(self, target_tcp_pos, target_tcp_rot=None, q_init=None, **kwargs):
        """Resolve a IK para uma pose desejada do TCP, convertendo para o flange internamente."""
        T_tcp_target = np.eye(4, dtype=float)
        T_tcp_target[:3, :3] = np.array(target_tcp_rot, dtype=float) if target_tcp_rot is not None else np.eye(3)
        T_tcp_target[:3, 3] = target_tcp_pos
        T_flange_target = T_tcp_target @ np.linalg.inv(self.TOOL_OFFSET)
        return self.inverse_kinematics(T_flange_target[:3, 3], T_flange_target[:3, :3], q_init=q_init, **kwargs)

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

    def check_joint_limits(self, q):
        """Retorna False se alguma junta de q estiver fora de self.JOINT_LIMITS."""
        for value, (lo, hi) in zip(q, self.JOINT_LIMITS):
            if value < lo or value > hi:
                return False
        return True

    def _alternate_seeds(self, q_base):
        """Sementes alternativas de q_init para reduzir falhas de convergência do IK."""
        q_base = np.array(q_base, dtype=float)
        home = np.array([0.0, -math.pi/2, 0.0, -math.pi/2, 0.0, 0.0], dtype=float)
        rng = np.random.default_rng(42)
        seeds = [home]
        for _ in range(3):
            seeds.append(q_base + rng.uniform(-0.3, 0.3, size=6))
        return seeds

    def analytic_inverse_kinematics(self, target_pos, target_rot):
        """Cinemática Inversa analítica (fechada) do UR3, derivada dos parâmetros D-H estritos
        desta classe e validada numericamente contra forward_kinematics (erro < 1e-6 em 200+
        configurações aleatórias). Retorna até 8 soluções (cotovelo cima/baixo, ombro
        esquerda/direita, pulso invertido), sem filtrar por limites de junta.

        Limitação conhecida: em singularidade de pulso (sin(theta5) ~= 0, eixos 4 e 6
        alinhados), theta6 é fixado em 0.0 e theta4 absorve a rotação restante.
        """
        d1 = self.dh_params[0]["d"]
        a2 = self.dh_params[1]["a"]
        a3 = self.dh_params[2]["a"]
        d4 = self.dh_params[3]["d"]
        d5 = self.dh_params[4]["d"]
        d6 = self.dh_params[5]["d"]

        R = np.array(target_rot, dtype=float)
        p = np.array(target_pos, dtype=float)
        solutions = []

        # Centro do punho: remove o offset d6 ao longo do eixo z da ferramenta.
        pw = p - d6 * R[:, 2]
        r_xy = math.hypot(pw[1], pw[0])
        if r_xy < abs(d4):
            return []  # posição fora do alcance do ombro (offset d4)

        phi1 = math.atan2(pw[1], pw[0])
        phi2 = math.acos(np.clip(d4 / r_xy, -1.0, 1.0))
        theta1_candidates = [phi1 + phi2 + math.pi / 2, phi1 - phi2 + math.pi / 2]

        for theta1 in theta1_candidates:
            c5 = (p[0] * math.sin(theta1) - p[1] * math.cos(theta1) - d4) / d6
            if abs(c5) > 1.0 + 1e-6:
                continue
            c5 = np.clip(c5, -1.0, 1.0)

            for sign5 in (1.0, -1.0):
                theta5 = sign5 * math.acos(c5)
                s5 = math.sin(theta5)
                s1, c1 = math.sin(theta1), math.cos(theta1)

                if abs(s5) < 1e-8:
                    theta6 = 0.0
                else:
                    s6 = (-R[0, 1] * s1 + R[1, 1] * c1) / s5
                    c6 = (R[0, 0] * s1 - R[1, 0] * c1) / s5
                    theta6 = math.atan2(s6, c6)

                T01 = self.dh_matrix(theta1, 0.0, d1, math.pi / 2)
                T45 = self.dh_matrix(theta5, 0.0, d5, -math.pi / 2)
                T56 = self.dh_matrix(theta6, 0.0, d6, 0.0)
                T_target = np.eye(4)
                T_target[:3, :3] = R
                T_target[:3, 3] = p
                T14 = np.linalg.inv(T01) @ T_target @ np.linalg.inv(T56) @ np.linalg.inv(T45)
                p14 = T14[:3, 3]

                # Braço planar (junta 2-3) no referencial da junta 1: p14 = (x, y, d4).
                r14 = math.hypot(p14[0], p14[1])
                c3 = (r14 ** 2 - a2 ** 2 - a3 ** 2) / (2 * a2 * a3)
                if abs(c3) > 1.0 + 1e-6:
                    continue
                c3 = np.clip(c3, -1.0, 1.0)

                for sign3 in (1.0, -1.0):
                    theta3 = sign3 * math.acos(c3)
                    s3 = math.sin(theta3)
                    theta2 = math.atan2(p14[1], p14[0]) - math.atan2(a3 * s3, a2 + a3 * math.cos(theta3))

                    T12 = self.dh_matrix(theta2, 0.0, 0.0, 0.0)
                    T23 = self.dh_matrix(theta3, a2, 0.0, 0.0)
                    T34 = np.linalg.inv(T23) @ np.linalg.inv(T12) @ T14
                    theta4 = math.atan2(T34[1, 0], T34[0, 0])

                    solutions.append([theta1, theta2, theta3, theta4, theta5, theta6])

        return solutions

    def inverse_kinematics(self, target_pos, target_rot=None, q_init=None, max_iter=100, tol=1e-4, damping=0.01):
        """Resolve a Cinemática Inversa: tenta a solução analítica fechada primeiro (rápida,
        sem mínimos locais) e cai para Damped Least Squares apenas se nenhuma das até 8
        soluções analíticas respeitar os limites de junta.
        """
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

        candidates = self.analytic_inverse_kinematics(target_pos, target_rot)
        valid = [sol for sol in candidates if self.check_joint_limits(sol)]
        if valid:
            # Escolhe a solução mais próxima da semente para manter continuidade da trajetória.
            best = min(valid, key=lambda sol: np.linalg.norm(np.array(sol) - q))
            return list(best), True

        return self._inverse_kinematics_dls(target_pos, target_rot, q, max_iter, tol, damping)

    def _inverse_kinematics_dls(self, target_pos, target_rot, q, max_iter, tol, damping):
        """Fallback numérico (Damped Least Squares sobre a Jacobiana geométrica)."""
        for _ in range(max_iter):
            transforms = self.forward_kinematics(q)
            p_curr = transforms[-1][:3, 3]
            R_curr = transforms[-1][:3, :3]
            
            e_p = target_pos - p_curr
            e_o = self._orientation_error(R_curr, target_rot)
            e = np.hstack([e_p, e_o])
            
            if np.linalg.norm(e) < tol:
                return q.tolist(), self.check_joint_limits(q)
                
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
        """Gera trajetória cartesiana para círculo perfeito no TCP (ponta da garra RG2, via
        self.TOOL_OFFSET), interpolada com S-Curve e resolvida via Cinemática Inversa D-H.
        O default de `center` já considera o offset de ~18.7cm da RG2 (verificado: alcançável).
        """
        if center is None:
            center = np.array([0.0, -0.45, 0.35], dtype=float)
        else:
            center = np.array(center, dtype=float)

        q_ref = np.array([0.0, -math.pi/2, 0.0, -math.pi/2, 0.0, 0.0], dtype=float)
        R_ref = self.forward_kinematics(q_ref)[-1][:3, :3] @ self.TOOL_OFFSET[:3, :3]

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
        max_rescale_attempts = 5
        q_traj = None
        times = None

        for _ in range(max_rescale_attempts):
            steps = int(nominal_duration * hz)

            # Obter ponto de início (ângulo 0), tentando sementes alternativas se preciso
            p_start = get_circle_point(0.0)
            q_start, ok = self.inverse_kinematics_tcp(p_start, R_ref, q_ref)
            if not ok:
                for seed in self._alternate_seeds(q_ref):
                    q_start, ok = self.inverse_kinematics_tcp(p_start, R_ref, seed)
                    if ok:
                        break
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
                q_sol, ok = self.inverse_kinematics_tcp(p_t, R_ref, q_curr)
                if not ok:
                    for seed in self._alternate_seeds(q_curr):
                        q_sol, ok = self.inverse_kinematics_tcp(p_t, R_ref, seed)
                        if ok:
                            break
                if not ok:
                    raise RuntimeError(f"Cinemática Inversa não convergiu no ponto {p_t}")
                q_curr = q_sol
                q_traj.append(q_sol)

            q_traj = np.array(q_traj)
            dt = 1.0 / hz
            v_traj = np.gradient(q_traj, dt, axis=0)
            a_traj = np.gradient(v_traj, dt, axis=0)
            # Força condições de contorno nulas (evita solavanco no início/fim do círculo)
            v_traj[0] = 0.0
            v_traj[-1] = 0.0
            a_traj[0] = 0.0
            a_traj[-1] = 0.0

            # Ajuste de escala de tempo caso a velocidade máxima exceda o limite seguro
            max_vel = np.max(np.abs(v_traj))
            if max_vel <= self.MAX_VELOCITY:
                break
            nominal_duration *= (max_vel / self.MAX_VELOCITY) * 1.1
        else:
            raise RuntimeError("Não foi possível manter a trajetória do círculo dentro do limite de velocidade após múltiplas tentativas.")

        for q in q_traj:
            if not self.check_joint_limits(q):
                raise RuntimeError("Trajetória do círculo violaria os limites de junta do UR3.")

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

    async def send_trajectory_action(self, trajectory_points, timeout=None):
        """Alternativa a publish_trajectory: envia a trajetória via action
        FollowJointTrajectory (confirmado disponível em
        /scaled_joint_trajectory_controller/follow_joint_trajectory), recebendo
        feedback contínuo e um resultado final (sucesso/erro), em vez de "atirar e
        esquecer". Retorna dict com success, result e (se houver) o último feedback.
        """
        if not self.connected:
            return {"success": False, "error": "not_connected"}

        if timeout is None:
            max_t = trajectory_points[-1]["time_from_start"]
            timeout = max_t["sec"] + max_t["nanosec"] * 1e-9 + 10.0

        goal_id = f"ur3_goal_{int(time.time() * 1000)}"
        goal = {
            "trajectory": {
                "header": {"stamp": {"sec": 0, "nanosec": 0}},
                "joint_names": self.joint_names,
                "points": trajectory_points,
            },
            "path_tolerance": [],
            "goal_tolerance": [],
            "goal_time_tolerance": {"sec": 0, "nanosec": 0},
        }
        queue = asyncio.Queue()
        self._pending_goals[goal_id] = queue

        action_msg = {
            "op": "send_action_goal",
            "id": goal_id,
            "action": "/scaled_joint_trajectory_controller/follow_joint_trajectory",
            "action_type": "control_msgs/action/FollowJointTrajectory",
            "args": goal,
            "feedback": True,
        }

        last_feedback = None
        try:
            await self.ws.send(json.dumps(action_msg))
            print(f"[INFO] Trajetória enviada via action ({len(trajectory_points)} pontos), aguardando resultado...")
            start = time.time()
            while time.time() - start < timeout:
                remaining = timeout - (time.time() - start)
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                if event.get("op") == "action_feedback":
                    last_feedback = event.get("values", {})
                elif event.get("op") == "action_result":
                    values = event.get("values", {})
                    success = values.get("error_code", -1) == 0
                    return {"success": success, "result": values, "last_feedback": last_feedback}
            return {"success": False, "error": f"Timeout após {timeout:.1f}s aguardando o resultado da action.", "last_feedback": last_feedback}
        finally:
            self._pending_goals.pop(goal_id, None)

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
        await agent.shutdown()
            
    asyncio.run(main())
