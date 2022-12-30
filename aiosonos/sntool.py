'''command-line interface to sonos network using aiosonos'''

import asyncio
import logging
import sys

import click

from . import sonos


_debug: int = 0


@click.group()
@click.option('--debug', default=0, help='Print more detailed information')
def main(debug):
    global _debug
    _debug = debug

    logging.basicConfig(
        format='[%(asctime)s %(levelname)-1.1s %(name)s] %(message)s',
        level=logging.WARNING,
        stream=sys.stderr)
    level_map = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
    }
    level = level_map.get(debug, logging.DEBUG - 1)
    logging.getLogger('aiosonos').setLevel(level)


@main.command()
def discover():
    asyncio.run(_discover())


@main.command()
def groups():
    asyncio.run(_groups())


async def _discover():
    player = await sonos.discover_one()
    print(player)
    await sonos.close()


async def _groups():
    player = await sonos.discover_one()
    network = await sonos.get_group_state(player)
    for group in network.groups:
        print(group)
        for player in group.members:
            print('  ' + player.describe())
    await sonos.close()


if __name__ == '__main__':
    main()
