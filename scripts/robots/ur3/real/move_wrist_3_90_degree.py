import asyncio
import math
import os
import sys

shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared"))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

from ur3_controller import UR3AutonomousController

async def main():
    agent = UR3AutonomousController()
    await agent.connect()

    if not agent.connected:
        print("[ERRO] Não foi possível conectar ao rosbridge.")
        return

    print("[INFO] Aguardando leitura do estado atual do robô (com validação de timestamp do hardware)...")
    try:
        current_state = await agent.fetch_current_state()
        print(f"[INFO] Posição atual das juntas: {current_state}")

        # Mover a junta 6 (index 5, wrist_3_joint), a mais próxima da garra, em +90 graus (pi/2 radianos)
        target_state = list(current_state)
        target_state[5] += math.pi / 2

        print(f"[INFO] Calculando trajetória S-Curve Sincronizada.")
        print(f"[INFO] Movendo Joint 6 (wrist_3_joint) de {current_state[5]:.4f} rad para {target_state[5]:.4f} rad")

        traj_points = agent.generate_cycloidal_trajectory(current_state, target_state)

        await agent.publish_trajectory(traj_points)

        # O robô executa a 20Hz. Esperar o tempo da trajetória terminar.
        tempo_estimado = len(traj_points) / 20.0
        print(f"[INFO] Trajetória enviada. Aguardando {tempo_estimado:.2f}s para a conclusão do movimento físico...")
        await asyncio.sleep(tempo_estimado + 1.0)
        print("[INFO] Movimento concluído.")

    except Exception as e:
        print(f"[ERRO CRÍTICO] Falha durante a operação: {e}")
    finally:
        agent.connected = False
        if agent.ws:
            await agent.ws.close()

if __name__ == "__main__":
    asyncio.run(main())
