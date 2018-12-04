"""
This is a standard HTTP proxy implementation.

See also https://imququ.com/post/web-proxy.html
"""

import asyncio
from urllib.parse import urlparse

from demo.utils import CaseInsensitiveDict


def split_host_port(host_port):
    try:
        host, port = host_port.rsplit(':', maxsplit=1)
    except ValueError:
        host = host_port
        port = 80
    return host, port


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(1024)
            writer.write(data)
            await writer.drain()
            if reader.at_eof():
                break
    except ConnectionError:
        pass


async def pipe_2way(reader1, writer1, reader2, writer2):
    task1 = asyncio.create_task(pipe(reader1, writer1))
    task2 = asyncio.create_task(pipe(reader2, writer2))
    await asyncio.wait([task1, task2])


class RequestHandler:
    def __init__(self,
                 reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.method = None
        self.path = None
        self.version = None
        self.headers = None

    async def handle(self):
        request_line = (await self.reader.readline()).decode().rstrip()
        self.method, self.path, self.version, *remained = request_line.split()
        if remained:
            await self.write_status(400)
            return

        self.headers = CaseInsensitiveDict()
        while True:
            header_line = (await self.reader.readline()).decode().strip()
            if not header_line:
                # empty line indicating the end of headers
                break
            else:
                key, value = header_line.split(':', maxsplit=1)
                self.headers[key.rstrip()] = value.lstrip()

        self.method = self.method.upper()
        print(f'{self.method} {self.path}')

        method = self.method.lower()
        method_handler = getattr(self, method, None)
        if method_handler:
            try:
                await method_handler()
            except ConnectionError:
                print(f'{self.method} {self.path} FAILED')
        else:
            await self.write_status(405)
            return

    async def write_status(self, status, reason=None):
        if reason is None:
            reason = {
                200: 'OK',
                400: 'Bad Request',
                405: 'Method Not Allowed',
            }.get(status)
        self.writer.write(f'{self.version} {status} {reason}\r\n'.encode())
        await self.writer.drain()

    async def write(self, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        try:
            self.writer.write(data)
            await self.writer.drain()
        except ConnectionError:
            pass

    def __getattr__(self, item):
        if item not in ('get', 'post', 'put', 'patch', 'delete', 'head'):
            return None

        return self.normal_method

    async def normal_method(self):
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

        svr_rd, svr_wt = await asyncio.open_connection(host, port)

        svr_wt.write(f'{self.method} {path} {self.version}\r\n'.encode())
        await svr_wt.drain()
        for key, value in self.headers.items():
            svr_wt.write(f'{key}: {value}\r\n'.encode())
            await svr_wt.drain()
        svr_wt.write(b'\r\n')
        await svr_wt.drain()

        await asyncio.wait_for(pipe_2way(self.reader, svr_wt,
                                         svr_rd, self.writer),
                               timeout=20)
        svr_wt.close()

    async def connect(self):
        host, port = split_host_port(self.path)

        svr_rd, svr_wt = await asyncio.open_connection(host, port)

        await self.write_status(200, 'Connection Established')
        await self.write('\r\n')
        await asyncio.wait_for(pipe_2way(self.reader, svr_wt,
                                         svr_rd, self.writer),
                               timeout=20)
        svr_wt.close()


async def handler(reader: asyncio.StreamReader,
                  writer: asyncio.StreamWriter):
    h = RequestHandler(reader, writer)
    try:
        await h.handle()
    except Exception:
        pass
    finally:
        writer.close()


async def main():
    server = await asyncio.start_server(handler, '127.0.0.1', 8080)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
