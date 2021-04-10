'''repeatedly show track/transport status for a single player'''

import argparse
import asyncio
import logging
import sys
import time

from aiosonos import api


async def main() -> None:
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.WARNING,
        stream=sys.stdout)

    parser = argparse.ArgumentParser()
    parser.add_argument('player')
    args = parser.parse_args()

    player = api.get_player(args.player)
    old_position = ''
    while True:
        track = await api.get_current_track_info(player)
        now = time.time()
        print('{now:.3f} {artist}: {title}  {position}/{duration} (was {old_position})'
              .format(now=now,
                      old_position=old_position,
                      **track),
              end='\r')

        await asyncio.sleep(0.1)
        old_position = track['position']


# with Python 3.7, we could use asyncio.run() here
asyncio.get_event_loop().run_until_complete(main())
