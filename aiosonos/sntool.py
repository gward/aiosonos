'''command-line interface to sonos network using aiosonos'''

import asyncio
import logging
import sys

import click

from . import models, sonos


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
@click.option('--all/--one', '-a/-1', 'discover_all',
              default=False, help='Wait for all players to be discovered')
@click.option('--timeout', '-t', default=1.0)
@click.option('--details', '-d', is_flag=True, help='Fetch detailed device description')
def discover(discover_all, timeout, details):
    task = _discover_all if discover_all else _discover_one
    asyncio.run(task(timeout, details))


@main.command()
def groups():
    asyncio.run(_groups())


async def _discover_one(timeout: float, details: bool):
    try:
        player = await sonos.discover_one(timeout)
        await _show_player(player, details)
    finally:
        await sonos.close()


async def _discover_all(timeout: float, details: bool):
    try:
        async for player in await sonos.discover_all(timeout):
            await _show_player(player, details)
    finally:
        await sonos.close()


async def _show_player(player: models.Player, details: bool):
    if details:
        desc = await sonos.get_player_description(player)
        print(f'{player.ip_address} {desc.udn} {desc.room_name!r} {desc.display_name!r}')
    else:
        print(f'{player.ip_address}')


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
