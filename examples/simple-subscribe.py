'''subscribe to certain events from a single player'''

import argparse
import asyncio
import logging
import signal
import sys

from aiosonos import sonos, upnp, event

log = logging.getLogger(__name__)


async def simple_subscribe(done_fut) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('player')
    args = parser.parse_args()
    player = sonos.get_player(args.player)

    def handle(event: event.Event) -> None:
        log.info('received event: %r with %d properties: %s',
                 event, len(event.properties), ', '.join(event.properties))

    log.debug('subscribing...')
    await sonos.subscribe(player, upnp.SERVICE_TOPOLOGY, handle, auto_renew=True)
    await sonos.subscribe(player, upnp.SERVICE_AVTRANSPORT, handle, auto_renew=True)
    log.debug('back from sonos.subscribe(): looping until done...')

    await done_fut


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
    loop.run_until_complete(simple_subscribe(done_fut))


main()
