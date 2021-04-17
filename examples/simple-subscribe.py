'''subscribe to certain events from a single player'''

import argparse
import asyncio
import logging
import sys

from aiosonos import sonos, upnp, event

log = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.DEBUG,
        stream=sys.stdout)

    parser = argparse.ArgumentParser()
    parser.add_argument('player')
    args = parser.parse_args()
    player = sonos.get_player(args.player)

    def handle(event: event.Event) -> None:
        log.info(repr(event))

    log.debug('subscribing...')
    await sonos.subscribe(player, upnp.SERVICE_TOPOLOGY, handle)
    # await sonos.subscribe(player, upnp.SERVICE_AVTRANSPORT, handle)
    log.debug('back from sonos.subscribe(): looping forever...')

    forever = asyncio.get_event_loop().create_future()
    return await forever


# with Python 3.7, we could use asyncio.run() here
asyncio.get_event_loop().run_until_complete(main())
