import asyncio
import base64
import json
import random
import struct
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Dict, Tuple, ClassVar

import websockets

from qdp import utils

MAGIC_PREFIX = '<<<42>>>~'
MTU = int(4500 * 3 / 4)  # bytes, 3/4 is because we will send base64
MAX_FRAGMENT_SIZE = MTU - len(MAGIC_PREFIX.encode('ascii'))

_qq_ws_base_url_mapping: Dict[int, str] = {}


def init(mapping: Dict[int, str]):
    global _qq_ws_base_url_mapping
    _qq_ws_base_url_mapping = mapping.copy()


class Socket:
    def __init__(self):
        self.addr = None
        self.cqhttp_ws_base_url = None
        self.cqhttp_ws_api = None
        self.cqhttp_ws_event = None

        # elem type: Tuple[src_qq, dst_qq, packet]
        self.recv_queue = None

    async def bind(self, addr: Tuple[int, Optional[int]]):
        qq, port = addr

        ws_base_url = _qq_ws_base_url_mapping.get(qq)
        if not ws_base_url:
            raise LookupError('there is no such qq that can be bound')

        if port is None:
            while port is None or (qq, port) in _socket_registry:
                port = random.randint(50000, 65535)
        else:
            if (qq, port) in _socket_registry:
                raise RuntimeError('the port specified is in use')

        self.addr = qq, port
        self.cqhttp_ws_base_url = ws_base_url
        self.recv_queue = asyncio.Queue()
        await self._connect_cqhttp()
        asyncio.create_task(self._listen_cqhttp_event())

        _socket_registry[self.addr] = self

    async def close(self):
        if self.cqhttp_ws_api:
            await self.cqhttp_ws_api.close()
            self.cqhttp_ws_api = None
        if self.cqhttp_ws_event:
            await self.cqhttp_ws_event.close()
            self.cqhttp_ws_event = None
        if self.addr in _socket_registry:
            del _socket_registry[self.addr]
            self.addr = None
        self.recv_queue = None

    async def sendto(self, data: bytes, addr: Tuple[int, int]):
        packet = Packet(src_port=self.addr[1],
                        dst_port=addr[1],
                        data=data)
        packet_data = packet.to_bytes()
        packet_id = random.randint(1, 65535)

        fragments = list()
        sequence = 1
        while len(packet_data) > Fragment.MAX_DATA_SIZE:
            fragments.append(Fragment(
                packet_id=packet_id,
                more_fragment=True,
                sequence=sequence,
                data=packet_data[:Fragment.MAX_DATA_SIZE]
            ))
            sequence += 1
            packet_data = packet_data[Fragment.MAX_DATA_SIZE:]
        fragments.append(Fragment(
            packet_id=packet_id,
            more_fragment=False,
            sequence=sequence,
            data=packet_data
        ))

        if self.cqhttp_ws_api:
            for fragment in fragments:
                fragment_data = fragment.to_bytes()
                msg = base64.b64encode(fragment_data).decode('ascii')
                await self.cqhttp_ws_api.send(json.dumps({
                    'action': 'send_private_msg_async_rate_limited',
                    'params': {
                        'user_id': addr[0],
                        'message': MAGIC_PREFIX + msg
                    }
                }))

    async def recvfrom(self) -> Tuple[bytes, Tuple[int, int]]:
        src_qq, _, packet = await self.recv_queue.get()
        return packet.data, (src_qq, packet.src_port)

    async def _connect_cqhttp(self):
        self.cqhttp_ws_api = await websockets.connect(
            self.cqhttp_ws_base_url.rstrip('/') + '/api/')
        self.cqhttp_ws_event = await websockets.connect(
            self.cqhttp_ws_base_url.rstrip('/') + '/event/')

    async def _listen_cqhttp_event(self):
        buffer = defaultdict(set)  # key: packet id, value: Set[fragment]
        while True:
            try:
                payload = json.loads(await self.cqhttp_ws_event.recv())
                if payload['post_type'] != 'message' or \
                        payload['message_type'] != 'private':
                    continue

                src_qq = payload['user_id']
                dst_qq = payload['self_id']
                msg = payload['message']

                if dst_qq != self.addr[0] or not msg.startswith(MAGIC_PREFIX):
                    continue

                msg = msg[len(MAGIC_PREFIX):]
                fragment_data = base64.b64decode(msg.encode('ascii'))
                fragment = Fragment.from_bytes(fragment_data)

                if fragment.more_fragment:
                    buffer[fragment.packet_id].add(fragment)
                else:
                    # the packet is fully received
                    fragment_set = buffer[fragment.packet_id]
                    del buffer[fragment.packet_id]

                    fragment_set.add(fragment)
                    fragments = sorted(fragment_set, key=lambda f: f.sequence)

                    if fragments[-1].sequence != len(fragments):
                        # there are some fragments missed, so drop it
                        continue

                    # construct the packet from fragments
                    packet_data = b''
                    for f in fragments:
                        packet_data += f.data
                    packet = Packet.from_bytes(packet_data)

                    if packet.dst_port != self.addr[1]:
                        # it's not for this socket
                        continue

                    await self.recv_queue.put(
                        (src_qq, dst_qq, packet)
                    )
            except (json.JSONDecodeError, KeyError):
                continue
            except websockets.exceptions.ConnectionClosed as e:
                if e.code != 1000:
                    await self._connect_cqhttp()
                else:
                    break


_socket_registry: Dict[Tuple[int, int], Socket] = {}


@dataclass(frozen=True)
class Packet:
    """
    Packet is similar to UDP packet.
    """
    src_port: int  # 16 bit
    dst_port: int  # 16 bit
    data: bytes  # variable length

    _HEAD_FMT: ClassVar[str] = '>HH'

    def __repr__(self):
        return f'Packet(src_port={self.src_port}, dst_port={self.dst_port}, ' \
               f'data={self.data})'

    def __hash__(self) -> int:
        return super().__hash__()

    def to_bytes(self):
        return struct.pack(self._HEAD_FMT,
                           self.src_port, self.dst_port) + self.data

    @classmethod
    def from_bytes(cls, data: bytes):
        (src_port, dst_port), data = utils.unpack_data(cls._HEAD_FMT, data)
        return cls(src_port, dst_port, data)


@dataclass(frozen=True)
class Fragment:
    """
    Fragment is similar to IP fragment.

    There are no "src_qq" and "dst_qq" fields because
    the two valued can be known from cqhttp's event data.
    """
    packet_id: int  # 16 bit
    more_fragment: bool  # 1 bit
    sequence: int  # 15 bit
    data: bytes  # variable length

    _HEAD_FMT: ClassVar[str] = '>HH'
    MAX_DATA_SIZE: ClassVar[int] = MAX_FRAGMENT_SIZE - \
                                   struct.calcsize(_HEAD_FMT)

    def __repr__(self):
        return f'Fragment(' \
               f'packet_id={self.packet_id}, ' \
               f'more_fragment={self.more_fragment}, ' \
               f'sequence={self.sequence}, ' \
               f'data={self.data})'

    def to_bytes(self):
        return struct.pack(
            self._HEAD_FMT,
            self.packet_id,
            (int(self.more_fragment) << 15) + self.sequence
        ) + self.data

    @classmethod
    def from_bytes(cls, data: bytes):
        (packet_id, tmp), data = utils.unpack_data(cls._HEAD_FMT, data)
        more_fragment, sequence = bool(tmp >> 15), tmp & 0x7FFF
        return cls(packet_id, more_fragment, sequence, data)
