import struct
from typing import Tuple, Any


def unpack_data(fmt: str,
                data_with_head: bytes) -> Tuple[Tuple[Any, ...], bytes]:
    head_size = struct.calcsize(fmt)
    return (struct.unpack(fmt, data_with_head[:head_size]),
            data_with_head[head_size:])
