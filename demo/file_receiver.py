import asyncio
import logging
import sys
import time

import qdp
from demo import config

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

qdp.init(config.CQHTTP_WS_URL_MAPPING)
logging.info('QDP service initialized')


async def main():
    sock = qdp.Socket()
    await sock.bind((3281334718, 10000))
    logging.info('QDP socket created')

    while True:
        data, addr = await sock.recvfrom()
        logging.info(f'Receive end: {time.time()}')
        logging.info(f'Received from {addr[0]}:{addr[1]}, '
                     f'data length: {len(data)}')
        with open('picture_received.jpg', 'wb') as f:
            f.write(data)
        await sock.sendto(b'OK', addr)


asyncio.run(main())
