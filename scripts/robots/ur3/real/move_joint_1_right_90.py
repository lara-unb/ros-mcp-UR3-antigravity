import sys
import os
import asyncio
import math

# Garantir que o módulo compartilhado ur3_controller seja encontrado
SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared"))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

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
        print(f"[INFO] Posição atual das juntas: {[round(q, 4) for q in current_state]}")
        
        # Mover a junta 1 (shoulder_pan_joint, index 0) em 90 graus para a direita (-pi/2 radianos)
        target_state = list(current_state)
        target_state[0] -= math.pi / 2
        
        print(f"[INFO] Calculando trajetória S-Curve Sincronizada (20 Hz, máx vel 0.15 rad/s)...")
        print(f"[INFO] Movendo Joint 1 (shoulder_pan) de {current_state[0]:.4f} rad para {target_state[0]:.4f} rad (-90.0°)")
        
        traj_points = agent.generate_cycloidal_trajectory(current_state, target_state, hz=20)
        
        await agent.publish_trajectory(traj_points)
        
        # O robô executa a 20Hz. Esperar o tempo da trajetória terminar.
        tempo_estimado = len(traj_points) / 20.0
        print(f"[INFO] Trajetória enviada. Duração calculada: {tempo_estimado:.2f}s. Aguardando conclusão...")
        await asyncio.sleep(tempo_estimado + 1.0)
        
        final_state = await agent.fetch_current_state()
        print(f"[INFO] Movimento concluído com sucesso!")
        print(f"[INFO] Posição final das juntas: {[round(q, 4) for q in final_state]}")
        
    except Exception as e:
        print(f"[ERRO CRÍTICO] Falha durante a operação: {e}")
    finally:
        agent.connected = False
        if agent.ws:
            await agent.ws.close()

if __name__ == "__main__":
    asyncio.run(main())
