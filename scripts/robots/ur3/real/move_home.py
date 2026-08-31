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
    await asyncio.sleep(1.0)
    await robot.move_to_home()
    await asyncio.sleep(1.0)
    if robot.ws:
        await robot.ws.close()

if __name__ == "__main__":
    asyncio.run(main())
