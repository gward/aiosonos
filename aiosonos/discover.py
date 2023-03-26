from __future__ import annotations

import asyncio
import asyncio.protocols
import asyncio.transports
import logging
import re
import socket
import struct
import sys
from typing import Any, AsyncGenerator, Coroutine, Optional, Tuple

from . import models, utils

log = logging.getLogger(__name__)


# Constants for multicast datagram.
PLAYER_SEARCH = b"""\
M-SEARCH * HTTP/1.1
HOST: 239.255.255.250:1900
MAN: "ssdp:discover"
MX: 1
ST: urn:schemas-upnp-org:device:ZonePlayer:1
"""
MULTICAST_GROUP = "239.255.255.250"
MULTICAST_PORT = 1900


def _create_udp_socket() -> socket.socket:
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM | socket.SOCK_NONBLOCK,
        socket.IPPROTO_UDP)
    # UPnP v1.0 requires a TTL of 4
    sock.setsockopt(
        socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('B', 4))
    # Do not set interface address: just use the system default.
    return sock


class DiscoveryProtocol(asyncio.protocols.DatagramProtocol):
    server_re = re.compile(
        rb'^server:.*\bsonos/', re.IGNORECASE | re.MULTILINE)

    def __init__(
            self,
            data: bytes,
            multicast_group: str,
            multicast_port: int,
            player_queue: 'asyncio.Queue[models.Player]'):
        self.data = data
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.player_queue = player_queue

    def close(self) -> None:
        if self.transport is not None:
            self.transport.close()

    def connection_made(self, transport: asyncio.transports.DatagramTransport) -> None:  # type: ignore # mypy wants BaseTransport # nopep8
        utils.log_network(
            log,
            'Discovery: multicasting to %s:%s',
            self.multicast_group,
            self.multicast_port,
            data=self.data)
        self.transport = transport
        self.transport.sendto(
            self.data, (self.multicast_group, self.multicast_port))

    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        # Only Zone Players should respond, given the value of ST in the
        # PLAYER_SEARCH message. However, to prevent misbehaved devices
        # on the network disrupting the discovery process, we check that
        # the response contains the "Sonos" string; otherwise we keep
        # waiting for a correct response.
        #
        # Here is a sample response from a real Sonos device (actual numbers
        # have been redacted):
        # HTTP/1.1 200 OK
        # CACHE-CONTROL: max-age = 1800
        # EXT:
        # LOCATION: http://***.***.***.***:1400/xml/device_description.xml
        # SERVER: Linux UPnP/1.0 Sonos/26.1-76230 (ZPS3)
        # ST: urn:schemas-upnp-org:device:ZonePlayer:1
        # USN: uuid:RINCON_B8*************00::urn:schemas-upnp-org:device:
        #                                                     ZonePlayer:1
        # X-RINCON-BOOTSEQ: 3
        # X-RINCON-HOUSEHOLD: Sonos_7O********************R7eU

        utils.log_network(
            log,
            'Discovery: received multicast response from %s:%s',
            addr[0],
            addr[1],
            data=data)
        if self.server_re.search(data):
            self.player_queue.put_nowait(models.Player(addr[0]))

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc is not None:
            log.info("UDP connection lost: %s", exc)


async def discover_one(timeout: float) -> models.Player:
    (player_queue, setup) = _setup_discover()
    (transport, protocol) = await setup
    try:
        return await asyncio.wait_for(player_queue.get(), timeout)
    finally:
        transport.close()


async def discover_all(timeout: float) -> AsyncGenerator[models.Player, None]:
    (player_queue, setup) = _setup_discover()
    (transport, protocol) = await setup
    try:
        while True:
            yield await asyncio.wait_for(player_queue.get(), timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        transport.close()


def _setup_discover() -> Tuple[asyncio.Queue[models.Player], Coroutine[Any, Any, Tuple]]:
    loop = utils.get_event_loop()
    player_queue: asyncio.Queue[models.Player] = asyncio.Queue()

    def factory() -> asyncio.protocols.BaseProtocol:
        return DiscoveryProtocol(
            PLAYER_SEARCH,
            MULTICAST_GROUP,
            MULTICAST_PORT,
            player_queue,
        )

    sock = _create_udp_socket()
    setup = loop.create_datagram_endpoint(factory, sock=sock)
    return (player_queue, setup)


if __name__ == '__main__':
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.DEBUG,
        stream=sys.stdout,
    )
    result = asyncio.get_event_loop().run_until_complete(discover_one(3.0))
    print(repr(result))
