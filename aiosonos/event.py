import asyncio
import logging
import socket
import time
from typing import Optional, Any, ClassVar, Callable, Dict, Tuple

import aiohttp
import aiohttp.client
from aiohttp import web
import multidict

from . import errors, models, parsers, upnp, utils

log = logging.getLogger(__name__)

# type aliases
EventCB = Callable[['Event'], None]


class Event:
    service: upnp.UPnPService
    sid: str
    seq: int
    properties: Dict[str, Any]

    def __init__(
            self,
            service: upnp.UPnPService,
            sid: str,
            seq: int,
            properties: Dict[str, Any]):
        self.service = service
        self.sid = sid
        self.seq = seq
        self.properties = properties

    def __str__(self):
        return '{service} {sid} #{seq}'.format(**vars(self))

    __repr__ = models.stdrepr


class Subscription:
    '''Represents one subscription to one service with one callback.'''

    # map from sid to Subscription in state 1, so we can cleanup
    _instances: ClassVar[Dict[str, 'Subscription']] = {}

    @classmethod
    def get_instance(cls, sid: str) -> Optional['Subscription']:
        return cls._instances.get(sid)

    @classmethod
    async def unsubscribe_all(cls) -> None:
        for sub in list(cls._instances.values()):
            await sub.unsubscribe()

    def __init__(
            self,
            session: aiohttp.client.ClientSession,
            player: models.Player,
            service: upnp.UPnPService,
            callback: EventCB):
        self.session = session
        self.player = player
        self.service = service
        self.callback = callback

        self.state = 0             # 0 = brand new, 1 = subscribed, 2 = unsubscribed

        # these will be set when we subscribe to something
        self.sid = ''
        self.timeout = -1
        self.timestamp = 0.0

    async def subscribe(self) -> None:
        if self.state != 0:
            raise errors.SonosError('Can only subscribe a brand-new Subscription object')

        auto_renew = False      # for now

        service = self.service
        base_url = self.player.base_url

        # Make sure we have a running EventServer (HTTP server that can
        # accept callback requests from the Sonos player)
        event_server = get_event_server()
        await event_server.ensure_running(self.player)

        # an event subscription looks like this:
        # SUBSCRIBE publisher path HTTP/1.1
        # HOST: publisher host:publisher port
        # CALLBACK: <delivery URL>
        # NT: upnp:event
        # TIMEOUT: Second-requested subscription duration (optional)

        callback_url = event_server.get_url()
        log.debug('event server running; callback url = %s', callback_url)
        req_headers = {
            "Callback": "<{}>".format(callback_url),
            "NT": "upnp:event",
        }

        response = await self.session.request(
            "SUBSCRIBE",
            base_url + service.event_subscription_url,
            headers=req_headers,
            timeout=3.0,
        )
        response.raise_for_status()

        headers = response.headers
        self.sid = headers["sid"]
        assert self.sid is not None

        # Register the subscription so it can be cleaned up
        self._instances[self.sid] = self

        timeout = headers["timeout"]
        # According to the spec, timeout can be "infinite" or "second-123"
        # where 123 is a number of seconds.  Sonos uses "Second-123"
        # (with a capital letter)
        if timeout.lower() == "infinite":
            self.timeout = -1
        else:
            self.timeout = int(timeout.lstrip("Second-"))
        self.timestamp = time.time()
        self.state = 1
        log.info(
            "Subscribed to %s: sid=%s, timeout=%d",
            base_url + service.event_subscription_url,
            self.sid,
            self.timeout,
        )

        # Set up auto_renew
        if not auto_renew or self.timeout is None:
            return
        # Autorenew just before expiry, say at 85% of self.timeout seconds
        # interval = self.timeout * 85 / 100
        # self._auto_renew_start(interval)

    async def unsubscribe(self) -> None:
        if self.state != 1:
            log.info('Nothing to unsubscribe')
            return

        req_headers = {
            "SID": self.sid,
        }
        response = await self.session.request(
            "UNSUBSCRIBE",
            self.player.base_url + self.service.event_subscription_url,
            headers=req_headers,
            timeout=1.0,
        )
        log.info('Unsubscribe response: %r', response)
        if response.status == 200:
            self.state = 2
            del self._instances[self.sid]

    async def _request(
            self,
            method: str,
            url: str,
            headers: Dict[str, str]) -> aiohttp.ClientResponse:
        return await self.session.request(
            method, url, headers=headers, timeout=3.0)

    def handle_event(self, event: Event):
        log.info('Subscription %s: received event %r', self.sid, event)
        self.callback(event)


class EventServer:
    '''HTTP server to handle callbacks from Sonos players'''
    server: Optional[web.Server]
    runner: web.ServerRunner
    url: str

    def __init__(self) -> None:
        self.server = None

    async def ensure_running(self, player: models.Player) -> None:
        if self.server is not None:
            return

        self.server = web.Server(self.handle)
        self.runner = web.ServerRunner(self.server)
        await self.runner.setup()

        ip_addr = await _get_local_addr(utils.get_event_loop(), player)
        site = web.TCPSite(self.runner, ip_addr, 0)
        await site.start()

        log.info('EventServer: ready for HTTP requests: site.name = %s',
                 site.name)

        # ugh: need to look at private attr site._server to determine the
        # real port that the kernel selected
        assert site._server is not None
        assert site._server.sockets is not None
        (addr, port) = site._server.sockets[0].getsockname()
        self.url = 'http://{}:{}/'.format(addr, port)

    def get_url(self) -> str:
        return self.url

    async def handle(self, request: web.BaseRequest) -> web.StreamResponse:
        '''Receive an HTTP NOTIFY request and emit an Event object.

        Also returns an HTTP response, but that's only visible to the Sonos
        player that sent the request, so not terribly important. What is
        important is parsing the request to create an Event object, which
        is then passed to the handle_event() method of the Subscription
        that caused this NOTIFY request to be sent. The Subscription is
        responsible for further processing, most importantly invoking the
        appropriate callback.
        '''

        # events on ZoneGroupTopology service look like
        # <e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
        #   <e:property>
        #     <ZoneGroupState>
        #       ...wrapped XML...
        #     </ZoneGroupState>
        #   </e:property>
        #   <e:property>...another property...</e:property>
        #   <e:property>...another property...</e:property>

        # events on AVTransport service look like
        #
        # <e:propertyset xmlns:e="urn:schemas-upnp-org:event-1-0">
        #   <e:property>
        #     <LastChange>
        #       ...wrapped XML....
        #     </LastChange>
        #   </e:property>
        # </e:propertyset>

        log.info('EventServer: received %s %s (path %s) headers:\n%s',
                 request.method, request.url, request.path, request.headers)
        body = await request.content.read()
        # log.debug('request body:\n%s', body)

        if (request.method == 'NOTIFY' and
                request.headers['content-type'] == 'text/xml'):
            (subscription, event) = self.parse_event(request.headers, body)
            if subscription is not None and event is not None:
                subscription.handle_event(event)

        return web.Response(text='')

    def parse_event(
            self,
            headers: 'multidict.CIMultiDictProxy[str]',
            body: bytes) -> Tuple[Optional[Subscription], Optional[Event]]:
        import pprint
        sid = headers['sid']       # event subscription id
        seq = int(headers['seq'])  # event sequence number
        subscription = Subscription.get_instance(sid)
        if subscription is None:
            log.warning('received event for unknown subscription: %s', sid)
            return (None, None)

        properties = parsers.parse_event_body(body)
        log.debug('parse_event_body returned properties:\n%s',
                  pprint.pformat(properties, indent=2, width=120))
        return (subscription, Event(subscription.service, sid, seq, properties))


async def _get_local_addr(
        loop: asyncio.AbstractEventLoop,
        player: models.Player) -> str:
    temp_sock = socket.socket(
        socket.AF_INET, socket.SOCK_DGRAM | socket.SOCK_NONBLOCK)
    with temp_sock:
        await loop.sock_connect(temp_sock, (player.ip_address, 1400))
        log.debug('temp_sock.getsockname() = %r', temp_sock.getsockname())
        return temp_sock.getsockname()[0]


_server = None


def get_event_server() -> EventServer:
    global _server
    if _server is None:
        _server = EventServer()
    return _server
