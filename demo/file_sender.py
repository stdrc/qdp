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
    await sock.bind((2474763007, None))
    logging.info('QDP socket created')

    addr = (3281334718, 10000)
    with open('picture.jpg', 'rb') as f:
        data = f.read()
    logging.info(f'Send begin: {time.time()}')
    await sock.sendto(data, addr)
    logging.info(f'Send end: {time.time()}')
    recv, _ = await sock.recvfrom()
    logging.info(recv.decode('utf-8'))
    await sock.close()


asyncio.run(main())
