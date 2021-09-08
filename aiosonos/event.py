import asyncio
import logging
import socket
import time
from typing import Optional, Any, ClassVar, Callable, Dict, List, Tuple

import aiohttp
import aiohttp.client
from aiohttp import web
import multidict

from . import errors, models, parsers, upnp, utils

log = logging.getLogger(__name__)

# type aliases
EventCB = Callable[['Event'], None]


class Event:
    subscription: 'Subscription'
    service_type: str
    player: models.Player
    seq: int
    properties: Dict[str, Any]

    def __init__(
            self,
            subscription: 'Subscription',
            seq: int,
            properties: Dict[str, Any]):
        self.subscription = subscription
        self.service_type = subscription.service.service_type
        self.player = subscription.player
        self.seq = seq
        self.properties = properties

    def __str__(self):
        return '{} {} #{}'.format(self.service_type, self.subscription.sid, self.seq)

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

    @classmethod
    def get_subscriptions(cls, player: models.Player) -> List['Subscription']:
        return [sub for sub in cls._instances.values() if sub.player is player]

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
        self.subscribe_url = ''
        self.timeout = -1
        self.timestamp = 0.0

        self.auto_renew_delay: Optional[int] = None
        self.auto_renew_task: Optional[asyncio.Task] = None

    def __str__(self):
        return self.sid or '?'

    __repr__ = models.stdrepr

    async def subscribe(self, auto_renew=False) -> None:
        if self.state != 0:
            raise errors.SonosError('Can only subscribe a brand-new Subscription object')

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
        req_headers = {
            "Callback": "<{}>".format(callback_url),
            "NT": "upnp:event",
        }

        self.subscribe_url = (self.player.base_url +
                              self.service.event_subscription_url)
        response = await self.session.request(
            "SUBSCRIBE",
            self.subscribe_url,
            headers=req_headers,
            timeout=3.0,
        )
        response.raise_for_status()

        headers = response.headers
        self.sid = headers["sid"]
        assert self.sid is not None

        # Register the subscription so it can be cleaned up
        self._instances[self.sid] = self

        self.timeout = self._parse_timeout(headers)
        self.timestamp = time.time()
        self.state = 1
        log.debug(
            'Subscription %s: subscribed (url=%s, timeout=%d, state=%d)',
            self,
            self.subscribe_url,
            self.timeout,
            self.state,
        )

        # Set up auto_renew
        if auto_renew and self.timeout > 0:
            if self.timeout <= 3600:
                self.auto_renew_delay = int(self.timeout * 0.95)
            else:
                self.auto_renew_delay = self.timeout - 180
            loop = utils.get_event_loop()
            # hmmmm, need to cancel this on shutdown
            self.auto_renew_task = loop.create_task(self._auto_renew_loop())

    async def _auto_renew_loop(self):
        assert self.auto_renew_delay is not None
        while True:
            await asyncio.sleep(self.auto_renew_delay)
            try:
                await self.renew()
            except Exception:
                log.exception('Subscription %s: failed to auto-renew (url=%s, state=%d)',
                              self, self.subscribe_url, self.state)

    async def renew(self) -> None:
        if self.state != 1:
            raise errors.SonosError('Can only renew a Subscription in subscribed state')

        log.info('Subscription %s: renewing (url=%s, state=%d)',
                 self, self.subscribe_url, self.state)

        req_headers = {
            "SID": self.sid,
        }

        response = await self.session.request(
            "SUBSCRIBE",
            self.subscribe_url,
            headers=req_headers,
            timeout=3.0,
        )
        response.raise_for_status()

        self.timeout = self._parse_timeout(response.headers)
        self.timestamp = time.time()
        log.debug(
            'Subscription %s: renewed (url=%s, state=%d)',
            self, self.subscribe_url, self.state)

    async def unsubscribe(self) -> None:
        if self.state != 1:
            log.info('Subscription %s: nothing to unsubscribe (state=%d)',
                     self, self.state)
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
        log.info('Subscription %s: unsubscribe response: %r %s',
                 self, response.status, response.reason)
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

    def _parse_timeout(self, headers: 'multidict.CIMultiDictProxy[str]') -> int:
        timeout = headers["timeout"]
        # According to the spec, timeout can be "infinite" or "second-123"
        # where 123 is a number of seconds.  Sonos uses "Second-123"
        # (with a capital letter)
        if timeout.lower() == "infinite":
            return -1
        return int(timeout.lstrip("Second-"))

    def handle_event(self, event: Event):
        log.info('Subscription %s: received event %r', self.sid, event)
        self.callback(event)


class EventServer:
    '''HTTP server to handle callbacks from Sonos players'''
    server: Optional[web.Server]
    runner: web.ServerRunner
    url: str

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
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

        # ugh: need to look at private attr site._server to determine the
        # real port that the kernel selected
        assert site._server is not None
        assert site._server.sockets is not None
        (addr, port) = site._server.sockets[0].getsockname()
        self.url = 'http://{}:{}/'.format(addr, port)
        log.info('EventServer: ready for HTTP requests: url = %s', self.url)

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

        log.debug('EventServer: received %s %s from %s',
                  request.method, request.path, request.remote)
        body = await request.content.read()

        if (request.method == 'NOTIFY' and
                request.headers['content-type'] == 'text/xml'):
            (subscription, event) = self.parse_event(request.headers, body)
            if subscription is not None and event is not None:
                # return response to the Sonos before handling the event
                self.loop.call_soon(subscription.handle_event, event)

        return web.Response(text='')

    def parse_event(
            self,
            headers: 'multidict.CIMultiDictProxy[str]',
            body: bytes) -> Tuple[Optional[Subscription], Optional[Event]]:
        # import pprint
        sid = headers['sid']       # event subscription id
        seq = int(headers['seq'])  # event sequence number
        subscription = Subscription.get_instance(sid)
        if subscription is None:
            log.warning('received event for unknown subscription: %s', sid)
            return (None, None)

        properties = parsers.parse_event_body(body)
        # log.debug('parse_event_body returned properties:\n%s',
        #           pprint.pformat(properties, indent=2, width=120))
        return (subscription, Event(subscription, seq, properties))


async def _get_local_addr(
        loop: asyncio.AbstractEventLoop,
        player: models.Player) -> str:
    temp_sock = socket.socket(
        socket.AF_INET, socket.SOCK_DGRAM | socket.SOCK_NONBLOCK)
    with temp_sock:
        await loop.sock_connect(temp_sock, (player.ip_address, 1400))
        return temp_sock.getsockname()[0]


_server = None


def get_event_server() -> EventServer:
    global _server
    if _server is None:
        _server = EventServer(utils.get_event_loop())
    return _server
