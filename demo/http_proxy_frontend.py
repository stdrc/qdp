import json
import uuid
import base64

import qdp
from demo import config
from demo.http_proxy import *

QDP_CLIENT_QQ = 2474763007
QDP_SERVER_QQ = 3281334718
QDP_SERVER_PORT = 20000
QDP_SERVER_ADDR = QDP_SERVER_QQ, QDP_SERVER_PORT

qdp.init(config.CQHTTP_WS_URL_MAPPING)
sock = qdp.Socket()


class CommandBridge:
    _futures = {}  # key: seq, value: asyncio.Future

    @classmethod
    async def send(cls, id_, method, params=None):
        if params is None:
            params = {}
        cmd = {
            'id': id_,
            'method': method,
            'params': params,
        }
        data = json.dumps(cmd, ensure_ascii=False).encode('utf-8')
        await sock.sendto(data, QDP_SERVER_ADDR)

    @classmethod
    async def listen(cls):
        while True:
            data, addr = await sock.recvfrom()
            if addr != QDP_SERVER_ADDR:
                continue

            cmd = json.loads(data.decode('utf-8'))
            cls._add_received(cmd)

    @classmethod
    def _add_received(cls, command):
        future = cls._futures.get(command.get('id'))
        if future:
            future.set_result(command)

    @classmethod
    async def receive(cls, id_):
        future = asyncio.get_event_loop().create_future()
        cls._futures[id_] = future
        try:
            return await asyncio.wait_for(future, 300)
        finally:
            # don't forget to remove the future object
            del cls._futures[id_]


async def pipe_f2b(reader, id_):
    try:
        while True:
            data = await reader.read(1024)
            print(f'{id_}, TRANSFER f2b:', data)
            await CommandBridge.send(id_, 'transfer', {
                'data': base64.b64encode(data).decode()
            })
            if reader.at_eof():
                break
    except ConnectionError:
        pass
    finally:
        await CommandBridge.send(id_, 'close')


async def pipe_b2f(id_, writer):
    try:
        while True:
            cmd = await CommandBridge.receive(id_)
            print(cmd)
            if cmd['method'] == 'close':
                print(f'{id_}, CLOSE')
                break

            if cmd['method'] == 'transfer':
                data = base64.b64decode(cmd['params']['data'])
                print(f'{id_}, TRANSFER b2f:', data)
                writer.write(data)
                await writer.drain()
    except ConnectionError:
        pass


async def pipe_2way(id_, reader, writer):
    task1 = asyncio.create_task(pipe_f2b(reader, id_))
    task2 = asyncio.create_task(pipe_b2f(id_, writer))
    await asyncio.wait([task1, task2])


class MyRequestHandler(RequestHandler):
    async def normal_method(self):
        id_ = str(uuid.uuid4())

        url = self.path
        p = urlparse(url)
        host, port = split_host_port(p.netloc)
        path = p.path
        if p.params:
            path += f';{p.params}'
        if p.query:
            path += f'?{p.query}'
        if p.fragment:
            path += f'#{p.fragment}'

        await CommandBridge.send(id_, 'connect', {'host': host, 'port': port})

        head = f'{self.method} {path} {self.version}\r\n'.encode()
        for key, value in self.headers.items():
            head += f'{key}: {value}\r\n'.encode()
        head += b'\r\n'
        await CommandBridge.send(id_, 'transfer', {
            'data': base64.b64encode(head).decode()
        })

        await asyncio.wait_for(pipe_2way(id_, self.reader, self.writer),
                               timeout=300)

    async def connect(self):
        id_ = str(uuid.uuid4())
        host, port = split_host_port(self.path)
        await CommandBridge.send(id_, 'connect', {'host': host, 'port': port})

        await self.write_status(200, 'Connection Established')
        await self.write('\r\n')
        await asyncio.wait_for(pipe_2way(id_, self.reader, self.writer),
                               timeout=300)


async def handler(reader: asyncio.StreamReader,
                  writer: asyncio.StreamWriter):
    h = MyRequestHandler(reader, writer)
    try:
        await h.handle()
    except Exception:
        pass
    finally:
        writer.close()


async def main():
    await sock.bind((QDP_CLIENT_QQ, None))
    asyncio.create_task(CommandBridge.listen())

    server = await asyncio.start_server(handler, '127.0.0.1', 8080)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
