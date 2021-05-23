'''query all groups in the Sonos network for their current queue'''

import asyncio
import logging
import sys

from aiosonos import sonos


async def main() -> None:
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.DEBUG,
        stream=sys.stdout)
    try:
        player = await sonos.discover_one()
        network = await sonos.get_group_state(player)

        for player in network.get_coordinators():
            queue = await sonos.get_queue(player)
            if not queue:
                print('{}: empty queue'.format(player))
            else:
                print('{}:'.format(player))
                for track in queue:
                    # print('  {}'.format(track))
                    # print('  attrs: {}'.format(vars(track)))
                    print('  {}: {} - {} ({})'.format(
                        track.id,
                        track.creator,
                        track.title,
                        track.album))
    finally:
        await sonos.close()

# with Python 3.7, we could use asyncio.run() here
asyncio.get_event_loop().run_until_complete(main())
