'''command-line interface to sonos network using aiosonos'''

import asyncio
import datetime
import logging
import sys

import click
from didl_lite import didl_lite as didl

from . import event, models, sonos, upnp


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


@main.group()
def queue():
    pass


@queue.command()
@click.argument('group')  # group ID, player ID, player IP address, or player name
def list(group: str):
    asyncio.run(_queue_list(group))


@queue.command()
@click.argument('group')
def clear(group: str):
    asyncio.run(_queue_clear(group))


@main.command()
def monitor():
    asyncio.run(_monitor())


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


async def _queue_list(group_id: str):
    try:
        group = await _find_group(group_id)
        tracks = await sonos.get_queue(group.coordinator)
        for track in tracks:
            uris = ','.join([res.uri for res in track.res])
            print(f'{track.id} {track.creator!r} {track.album!r} {track.title!r} {uris}')
    finally:
        await sonos.close()


async def _queue_clear(group_id: str):
    try:
        group = await _find_group(group_id)
        await sonos.clear_queue(group.coordinator)
    finally:
        await sonos.close()


async def _monitor():
    def ts():
        return str(datetime.datetime.now())

    def topology_cb(event: event.Event):
        network = event.properties.get('ZoneGroupState')
        details = ''
        if isinstance(network, models.Network):
            details = (' group coordinators: ' +
                       ','.join(coord.ip_address for coord in network.get_coordinators()))
        print(f'{ts()} {event.service_type}: {event.player}{details}')

    def transport_cb(event: event.Event):
        transport_state = event.properties['TransportState']
        track_num = event.properties['CurrentTrack']
        track_duration = event.properties['CurrentTrackDuration']
        track = event.properties['CurrentTrackMetaData']
        details = ' (no track metadata)'
        if isinstance(track, didl.MusicTrack):
            details = (f': track {track_num} '
                       f'{track.creator!r} {track.title!r} {track_duration}')
        print(f'{ts()} {event.service_type}: '
              f'{event.player} {transport_state}{details}')

    # Get all groups and subscribe to interesting events.
    try:
        # Only need topology events from one player.
        player = await sonos.discover_one()
        await sonos.subscribe(
            player, upnp.SERVICE_TOPOLOGY, topology_cb, auto_renew=True)

        # For other events, subscribe to each group coordinator.
        network = await sonos.get_group_state(player)
        for group in network.groups:
            await sonos.subscribe(
                group.coordinator,
                upnp.SERVICE_AVTRANSPORT,
                transport_cb,
                auto_renew=True)

        while True:
            await asyncio.sleep(1)

    finally:
        await sonos.close()


async def _find_group(group_id: str) -> models.Group:
    player = await sonos.discover_one()
    network = await sonos.get_group_state(player)
    group = coordinator = None
    for group in network.groups:
        coordinator = group.coordinator
        if group.uuid == group_id:
            return group
        if coordinator.uuid == group_id:
            return group
        if coordinator.ip_address == group_id:
            return group
        if coordinator.name is not None and group_id.lower() in coordinator.name.lower():
            return group
    else:
        sys.exit(f'sntool: error: found no group identified by "{group_id}"')


if __name__ == '__main__':
    main()
