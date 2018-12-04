import asyncio
import json
import base64

import qdp
from demo import config

QDP_SERVER_QQ = 3281334718
QDP_SERVER_PORT = 20000
QDP_SERVER_ADDR = QDP_SERVER_QQ, QDP_SERVER_PORT

qdp.init(config.CQHTTP_WS_URL_MAPPING)
sock = qdp.Socket()

cmd_queues = {}


class CommandBridge:
    @classmethod
    async def send(cls, addr, id_, method, params=None):
        if params is None:
            params = {}
        cmd = {
            "id": id_,
            'method': method,
            'params': params,
        }
        data = json.dumps(cmd, ensure_ascii=False).encode('utf-8')
        await sock.sendto(data, addr)


async def pipe_b2f(reader, addr, id_):
    try:
        while True:
            data = await reader.read(1024)
            print(f'{id_}, TRANSFER b2f:', data)
            await CommandBridge.send(addr, id_, 'transfer', {
                'data': base64.b64encode(data).decode()
            })
            if reader.at_eof():
                break
    except ConnectionError:
        pass


async def real_handle(addr, connect_cmd, cmd_queue):
    id_ = connect_cmd['id']

    host = connect_cmd['params']['host']
    port = connect_cmd['params']['port']
    print(f'{id_}, CONNECT {host}:{port}')

    try:
        reader, writer = await asyncio.open_connection(host, port)

        asyncio.create_task(pipe_b2f(reader, addr, id_))

        while True:
            cmd = await cmd_queue.get()
            print(cmd)

            if cmd['method'] == 'close':
                print(f'{id_}, CLOSE')
                return

            if cmd['method'] == 'transfer':
                data = base64.b64decode(cmd['params']['data'])
                print(f'{id_}, TRANSFER f2b:', data)
                writer.write(data)
                await writer.drain()
    except Exception:
        pass
    finally:
        await CommandBridge.send(addr, id_, 'close')


async def handle(addr, connect_cmd, cmd_queue):
    await asyncio.wait_for(
        asyncio.ensure_future(real_handle(addr, connect_cmd, cmd_queue)),
        timeout=300
    )


async def main():
    await sock.bind(QDP_SERVER_ADDR)

    while True:
        data, addr = await sock.recvfrom()
        try:
            cmd = json.loads(data.decode('utf-8'))
        except json.JSONDecodeError:
            continue

        if cmd['method'] == 'connect':
            cmd_queue = asyncio.Queue()
            cmd_queues[cmd['id']] = cmd_queue
            asyncio.ensure_future(handle(addr, cmd, cmd_queue))
        elif cmd['id'] in cmd_queues:
            cmd_queues[cmd['id']].put_nowait(cmd)
            if cmd['method'] == 'close':
                del cmd_queues[cmd['id']]


asyncio.run(main())
