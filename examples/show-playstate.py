'''show the current play state of a single player'''

import argparse
import asyncio
import logging
import sys

from aiosonos import sonos


async def main() -> None:
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.DEBUG,
        stream=sys.stdout)

    parser = argparse.ArgumentParser()
    parser.add_argument('player')
    args = parser.parse_args()

    try:
        player = sonos.get_player(args.player)
        track_info = await sonos.get_current_track_info(player)
        transport_info = await sonos.get_transport_info(player)
        queue = await sonos.get_queue(player)

        print('track_info:', track_info)
        print('transport_info:', transport_info)
        print('queue:', queue)
    finally:
        await sonos.close()


asyncio.get_event_loop().run_until_complete(main())
