import asyncio
import asyncio.protocols
import asyncio.transports
import logging
import re
import socket
import struct
import sys
from typing import Optional, Tuple

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


class DiscoveryProtocol(asyncio.protocols.BaseProtocol):
    """implements asyncio.protocols.DatagramProtocol interface"""
    server_re = re.compile(
        rb'^server:.*\bsonos/', re.IGNORECASE | re.MULTILINE)

    def __init__(
            self,
            data: bytes,
            multicast_group: str,
            multicast_port: int,
            player_fut: asyncio.Future):
        self.data = data
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.player_fut = player_fut

    def connection_made(self, transport: asyncio.transports.DatagramTransport) -> None:  # type: ignore # mypy wants BaseTransport # nopep8
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

        log.debug('DiscoveryProtocol.datagram_received: addr = %s', addr)
        if self.server_re.search(data):
            self.player_fut.set_result(models.Player(addr[0]))
            self.transport.close()

    def error_received(self, exc: Exception):
        self.player_fut.set_exception(exc)

    def connection_lost(self, exc: Optional[Exception]) -> None:
        if exc is not None:
            log.info("UDP connection lost: %s", exc)


async def discover_one(timeout) -> models.Player:
    loop = utils.get_event_loop()
    player_fut = loop.create_future()

    def factory() -> asyncio.protocols.BaseProtocol:
        return DiscoveryProtocol(
            PLAYER_SEARCH,
            MULTICAST_GROUP,
            MULTICAST_PORT,
            player_fut,
        )

    # XXX SoCo allows caller to specify interface address
    # XXX SoCo goes to lots of trouble to figure out the right interface
    sock = _create_udp_socket()
    (transport, protocol) = await loop.create_datagram_endpoint(
        factory, sock=sock)
    return await asyncio.wait_for(player_fut, timeout)


if __name__ == '__main__':
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.DEBUG,
        stream=sys.stdout,
    )
    result = asyncio.get_event_loop().run_until_complete(discover_one(3.0))
    print(repr(result))
