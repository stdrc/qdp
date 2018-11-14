import asyncio
import logging
import sys

import qdp
from demo import config

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

qdp.init(config.CQHTTP_WS_BASE_URL_MAPPING)
logging.info('QDP service initialized')


async def main():
    sock = qdp.Socket()
    await sock.bind((3281334718, 12345))
    logging.info('QDP socket created')

    while True:
        data, addr = await sock.recvfrom()
        text = data.decode('utf-8')
        logging.info(f'Received from {addr[0]}:{addr[1]}, data: {text}')
        text_send = 'Hello, %s!' % text
        await sock.sendto(text_send.encode('utf-8'), addr)
        logging.info(f'Sent to {addr[0]}:{addr[1]}, data: {text_send}')


asyncio.run(main())
