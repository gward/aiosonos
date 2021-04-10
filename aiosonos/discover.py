import asyncio
import logging
import re
import select
import socket
import struct
import sys
import time

from . import models

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


# XXX omits include_invisible
# XXX ignores interface_addr
def discover_one_sync(
        timeout: float = 5.0,
        interface_addr: str = None) -> models.Player:
    '''Discover an arbitrary Sonos player on the local network.

    Send a discovery packet by UDP multicast, and return a player object
    for the first player that responds.
    '''

    # sockets: List[socket.socket] = []

    # def add_socket(addr):
    #     try:
    #         socket = _create_udp_socket(addr)
    #     except socket.error as err:
    #         log.warning('Failed to make discovery socket for %s: %s: %s',
    #                     addr, type(err).__name__, err)
    #     else:
    #         sockets.append(socket)

    # if interface_addr is not None:
    #     ipaddress.ip_address(interface_addr)    # provoke ValueError if bogus
    #     add_socket(interface_addr)
    # else:
    #     # Find the local network address using a couple of different methods.
    #     # Create a socket for each unique address found, and one for the
    #     # default multicast address
    #     addr = socket.gethostbyname(socket.gethostname())
    #     add_socket(addr)

    #     addr = socket.gethostbyname(socket.getfqdn())
    #     add_socket(addr)

    # if not sockets:
    #     raise SonosError('Unable to create any discovery sockets')

    sock = _create_udp_socket()

    # Send the discovery datagram.
    sock.sendto(PLAYER_SEARCH, (MULTICAST_GROUP, MULTICAST_PORT))

    now = time.monotonic()
    deadline = now + timeout
    while True:
        log.debug('select: now = %.1f, deadline = %.1f, timeout = %.1f',
                  now, deadline, deadline - now)
        (ready, _, _) = select.select([sock], [], [], deadline - now)
        log.debug('ready: %r', ready)

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
        if ready:
            for sock in ready:
                (data, addr) = sock.recvfrom(1024)
                log.debug('discovery response from %s:\n%s', addr, data.decode())
                # Now we have an IP, we can immediately return a Player
                # instance. It is much more efficient to use the Zone
                # Player's ability to find the others than to wait for
                # query responses from them ourselves.
                if b'Sonos' in data:
                    return models.Player(addr[0])

        now = time.monotonic()


def _create_udp_socket() -> socket.socket:
    sock = socket.socket(
        socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    # UPnP v1.0 requires a TTL of 4
    sock.setsockopt(
        socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('B', 4))
    # Do not set interface address: just use the system default.
    return sock


class DiscoveryProtocol:
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

    def connection_made(self, transport):
        log.debug('DiscoveryProtocol: connection_made, transport=%r', transport)
        self.transport = transport
        self.transport.sendto(
            self.data, (self.multicast_group, self.multicast_port))

    def datagram_received(self, data, addr):
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

        log.debug('DiscoveryProtocol: datagram received from addr %s:\n%s',
                  addr, data.decode())
        if self.server_re.search(data):
            self.player_fut.set_result(models.Player(addr[0]))
            self.transport.close()

    def connection_lost(lost, self):
        log.debug("DiscoveryProtocol: connection lost")


async def discover_one():
    loop = asyncio.get_event_loop()     # switch to get_running_loop in 3.7
    player_fut = loop.create_future()

    def factory():
        return DiscoveryProtocol(
            PLAYER_SEARCH,
            MULTICAST_GROUP,
            MULTICAST_PORT,
            player_fut,
        )

    # XXX timeout?
    sock = _create_udp_socket()
    (transport, protocol) = await loop.create_datagram_endpoint(
        factory, sock=sock)
    return await player_fut


use_asyncio = True

if __name__ == '__main__':
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.DEBUG,
        stream=sys.stdout,
    )
    if use_asyncio:
        result = asyncio.get_event_loop().run_until_complete(discover_one())
        print(repr(result))
    else:
        print("discover_one() returned:", discover_one())
