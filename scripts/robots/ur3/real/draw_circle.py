import asyncio
import os
import sys

shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared"))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

from ur3_controller import UR3AutonomousController

async def main():
    robot = UR3AutonomousController()
    await robot.connect()
    
    # 1. Obter telemetria do robô
    print("[INFO] Aguardando leitura das juntas...")
    current_joints = await robot.fetch_current_state()
    print(f"[INFO] Juntas atuais lidas com sucesso: {current_joints}")
    
    # 2. Parâmetros do círculo (posição da ponta da garra RG2, já considerando o TOOL_OFFSET)
    center = [0.0, -0.45, 0.35]
    radius = 0.06  # 6 cm de raio (12 cm de diâmetro)
    plane = "xz"
    
    print(f"[INFO] Planejando círculo perfeito no plano {plane.upper()} centrado em {center} com raio de {radius}m...")
    circle_points, q_start = robot.generate_cartesian_circle_trajectory(
        center=center, 
        radius=radius, 
        plane=plane, 
        hz=20
    )
    
    # 3. Trajetória de aproximação até o início do círculo
    print("[INFO] Gerando aproximação suave até o ponto inicial do círculo...")
    approach_points = robot.generate_cycloidal_trajectory(current_joints, q_start, hz=20)
    approach_duration = approach_points[-1]["time_from_start"]["sec"] + approach_points[-1]["time_from_start"]["nanosec"] * 1e-9
    
    # Publicar aproximação
    print(f"[INFO] Executando aproximação ({approach_duration:.2f}s)...")
    await robot.publish_trajectory(approach_points)
    await asyncio.sleep(approach_duration + 0.5)
    
    # 4. Executar o círculo perfeito
    circle_duration = circle_points[-1]["time_from_start"]["sec"] + circle_points[-1]["time_from_start"]["nanosec"] * 1e-9
    print(f"[INFO] Executando círculo perfeito ({circle_duration:.2f}s, {len(circle_points)} pontos)...")
    await robot.publish_trajectory(circle_points)
    await asyncio.sleep(circle_duration + 0.5)
    
    print("[INFO] Círculo perfeito concluído com sucesso!")
    if robot.ws:
        await robot.ws.close()

if __name__ == "__main__":
    asyncio.run(main())
