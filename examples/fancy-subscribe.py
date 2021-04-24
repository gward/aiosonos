'''subscribe to all group coordinators to monitor the whole network'''

import asyncio
import logging
import signal
import sys
from typing import Set

from aiosonos import sonos, utils, models, upnp, event

log = logging.getLogger()


async def fancy_subscribe(done_fut) -> None:
    loop = utils.get_event_loop()
    player = await sonos.discover_one()
    log.info('discovered player: %r', player)

    old_coordinators: Set[models.Player] = set()

    def topology_callback(evt: event.Event):
        nonlocal old_coordinators

        network = evt.properties['ZoneGroupState']
        log.info('received topology event: ZoneGroupState = %r', network)
        new_coordinators = {group.coordinator for group in network.groups}

        added = new_coordinators - old_coordinators
        dropped = old_coordinators - new_coordinators

        for player in dropped:
            for sub in sonos.get_subscriptions_for_player(player):
                log.info('Ex-coordinator %r: unsubscribing from %s',
                         sub.player, sub)
                loop.create_task(sub.unsubscribe())

        for player in added:
            log.info('New coordinator %r: subscribing to AVTransport service',
                     player)
            loop.create_task(sonos.subscribe(
                player, upnp.SERVICE_AVTRANSPORT, transport_callback, auto_renew=True))

        old_coordinators = new_coordinators

    def transport_callback(evt):
        # import pprint
        # log.info('received transport event: %r:\n%s',
        #          evt, pprint.pformat(vars(evt), width=120))
        log.info('received transport event: %r', evt)

    await sonos.subscribe(
        player, upnp.SERVICE_TOPOLOGY, topology_callback, auto_renew=True)

    await done_fut
    await sonos.close()


async def interrupted(loop, done_fut):
    print('start cleanup')
    try:
        await sonos.close()
    except Exception:
        log.exception('error closing aiosonos library')
    done_fut.set_result(True)
    loop.call_soon(loop.stop)
    print('done cleanup: will stop soon')


def main() -> None:
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.DEBUG,
        stream=sys.stdout)

    loop = asyncio.get_event_loop()
    done_fut = loop.create_future()
    loop.add_signal_handler(
        signal.SIGINT, lambda: asyncio.ensure_future(interrupted(loop, done_fut)))
    # with Python 3.7, we could use asyncio.run() here
    loop.run_until_complete(fancy_subscribe(done_fut))


main()
