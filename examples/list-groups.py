#!venv/bin/python

"""use aiosonos to list all groups and players in the local Sonos network"""

import asyncio
import logging
import sys

from aiosonos import discover, api, upnp


async def main():
    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.DEBUG,
        stream=sys.stdout)
    player = await discover.discover_one()
    print(repr(player))
    network = await api.get_group_state(player)
    print('groups:')
    for group in network.groups:
        print('  {}'.format(group))
        for player in group.members:
            print('    ' + player.describe())
    print('visible players:')
    for player in network.visible_players:
        print('  ' + player.describe())
    print('all players:')
    for player in network.all_players:
        print('  ' + player.describe())
    assert upnp._session is not None
    await upnp._session.close()


# with Python 3.7, we could use asyncio.run() here
asyncio.get_event_loop().run_until_complete(main())
