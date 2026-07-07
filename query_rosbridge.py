import asyncio
import json
import websockets

async def get_topics():
    try:
        async with websockets.connect('ws://localhost:9090') as websocket:
            msg = {
                "op": "call_service",
                "service": "/rosapi/topics"
            }
            await websocket.send(json.dumps(msg))
            response = await websocket.recv()
            data = json.loads(response)
            print("Tópicos encontrados:", data.get('values', {}).get('topics', []))
    except Exception as e:
        print("Erro ao conectar:", e)

asyncio.run(get_topics())
