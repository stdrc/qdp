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
    await sock.bind((2910007356, None))
    logging.info('QDP socket created')

    addr = (3281334718, 12345)
    for text in ['你好', 'hello', '123']:
        await sock.sendto(text.encode('utf-8'), addr)
        logging.info(f'Sent to {addr[0]}:{addr[1]}, data: {text}')
        data, _ = await sock.recvfrom()
        text_recv = data.decode('utf-8')
        logging.info(f'Received: {text_recv}')

    await sock.close()


asyncio.run(main())
