import asyncio
import os
import sys

import numpy as np

shared_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../shared"))
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)

from ur3_controller import UR3AutonomousController

# Frame da base do UR3: "à frente" é -y (mesma convenção do home e do draw_circle.py).
CUP_FORWARD = 0.42          # distância do copo à frente da base (m)
CUP_Z = -0.25               # altura do copo em relação à base (m)
CUP_RADIUS = 0.04           # raio assumido do copo (m)
PUSH_HEIGHT = CUP_Z + 0.03  # altura do TCP no empurrão: atinge o copo tanto se CUP_Z for a base quanto o centro
STANDOFF = 0.06             # folga entre o TCP e a borda do copo antes de empurrar (m)
PUSH_DISTANCE = 0.07        # quanto empurrar após o contato (m)
SAFE_Z = 0.05               # altura segura para aproximação/retirada (m)

# Ferramenta apontando para baixo (z do TCP = -z da base), dedos fechados empurrando o copo.
R_TOOL_DOWN = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]])


async def run_segment(robot, name, points, dry_run):
    duration = points[-1]["time_from_start"]["sec"] + points[-1]["time_from_start"]["nanosec"] * 1e-9
    print(f"[INFO] {name}: {len(points)} pontos, {duration:.1f}s")
    if dry_run:
        return
    await robot.publish_trajectory(points)
    await asyncio.sleep(duration + 0.5)
    # A action FollowJointTrajectory não está disponível no rosbridge atual (sem control_msgs),
    # então a conclusão é confirmada pela telemetria.
    final = await robot.fetch_current_state()
    error = np.max(np.abs(np.array(final) - np.array(points[-1]["positions"])))
    if error > 0.02 or not robot.connected:
        raise RuntimeError(f"Segmento '{name}' não chegou ao alvo (erro máx. {error:.3f} rad).")


async def main(dry_run=False):
    robot = UR3AutonomousController()
    await robot.connect()
    try:
        q0 = await robot.fetch_current_state()
        print(f"[INFO] Juntas atuais: {q0}")

        y_start = -(CUP_FORWARD - CUP_RADIUS - STANDOFF)
        y_end = y_start - STANDOFF - PUSH_DISTANCE
        above = [0.0, y_start, SAFE_Z]
        start = [0.0, y_start, PUSH_HEIGHT]
        end = [0.0, y_end, PUSH_HEIGHT]
        print(f"[INFO] Empurrão do TCP: y {y_start:.2f} -> {y_end:.2f} m a z={PUSH_HEIGHT:.2f} m")

        q_above, ok = robot.inverse_kinematics_tcp(above, R_TOOL_DOWN, q0)
        if not ok:
            raise RuntimeError("Ponto de aproximação inalcançável.")

        approach = robot.generate_cycloidal_trajectory(q0, q_above)
        descend, _, q = robot.generate_cartesian_line_trajectory(above, start, R_TOOL_DOWN, q_above)
        push, _, q = robot.generate_cartesian_line_trajectory(start, end, R_TOOL_DOWN, q, min_duration=8.0)
        retreat, _, q = robot.generate_cartesian_line_trajectory(end, start, R_TOOL_DOWN, q, min_duration=4.0)
        lift, _, q = robot.generate_cartesian_line_trajectory(start, above, R_TOOL_DOWN, q)

        for name, pts in [("aproximação", approach), ("descida", descend), ("empurrão", push),
                          ("recuo", retreat), ("subida", lift)]:
            await run_segment(robot, name, pts, dry_run)
        print("[INFO] Concluído." if not dry_run else "[INFO] Dry-run concluído (nada foi enviado).")
    finally:
        await robot.shutdown()


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
