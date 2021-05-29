'''The public interface to aiosonos.

If it's in this module, you should assume the interface is reasonably stable
and won't break after aiosonos 1.0 is released. Otherwise, all bets are off.
You can call code in other modules, but it might break.

Also, nothing else in aiosonos is allowed to depend on this module. If you
are writing code that will be used elsewhere in aiosonos, this is the wrong
place.
'''

import logging
from xml.etree import ElementTree
from typing import Any, Dict, List

from didl_lite import didl_lite as didl

from . import models, upnp, discover, event, parsers

log = logging.getLogger(__name__)


async def discover_one() -> models.Player:
    '''Discover the local Sonos network and return one arbitrary Player.

    Send a UPnP discovery packet and wait for responses to arrive. As soon
    as one arrives, construct a Player object based on that response and
    return it. Ignore any further responses.
    '''
    return await discover.discover_one()


def get_player(ip_address: str) -> models.Player:
    '''Return a Player object for the given IP address.

    Performs no I/O and does not validate that the IP address is actually
    a Sonos player.

    This function has singleton-like semantics: if a Player does not yet
    exist for ``ip_address``, create and return one; for a given
    ``ip_address``, always return the same object.
    '''
    return models.Player.get_instance(ip_address)


async def get_group_state(player: models.Player) -> models.Network:

    # # XXX SoCo caches both the raw XML and the parsed result: worth it?
    # now = time.monotonic()
    # if (self._group_state_update is not None and
    #         now - self._group_state_update <= self.group_state_ttl):
    #     return

    client = upnp.get_upnp_client(player)
    result = await client.send_command(
        upnp.SERVICE_TOPOLOGY,
        'GetZoneGroupState')
    groups_xml = result['ZoneGroupState']
    return parsers.parse_group_state(groups_xml)


async def get_current_track_info(player: models.Player) -> Dict[str, Any]:
    '''Get information about the currently playing track.

    Returns:
        dict: A dictionary containing information about the currently
        playing track: playlist_position, duration, title, artist, album,
        position and an album_art link.

    If we're unable to return data for a field, we'll return an empty
    string. This can happen for all kinds of reasons so be sure to check
    values. For example, a track may not have complete metadata and be
    missing an album name. In this case track['album'] will be an empty
    string.

    .. note:: Calling this method on a slave in a group will not
        return the track the group is playing, but the last track
        this speaker was playing.
    '''
    client = upnp.get_upnp_client(player)
    result = await client.send_command(
        upnp.SERVICE_AVTRANSPORT,
        'GetPositionInfo',
        [('InstanceID', 0), ('Channel', 'Master')]
    )
    log.debug('GetPositionInfo result: %r', result)
    return _parse_track_info(result)


def _parse_track_info(result: Dict[str, Any]) -> Dict[str, Any]:
    track = {
        'title': '',
        'artist': '',
        'album': '',
        'album_art': '',
        'position': '',
    }
    track['playlist_position'] = result['Track']
    track['duration'] = result['TrackDuration']
    track['uri'] = result['TrackURI']
    track['position'] = result['RelTime']

    metadata = result['TrackMetaData']
    # Store the entire Metadata entry in the track, this can then be
    # used if needed by the client to restart a given URI
    track['metadata'] = metadata
    # Duration seems to be '0:00:00' when listening to radio
    if metadata != '' and track['duration'] == '0:00:00':
        metadata = ElementTree.fromstring(metadata)
        # Try parse trackinfo
        trackinfo = (
            metadata.findtext(
                './/{urn:schemas-rinconnetworks-com:' 'metadata-1-0/}streamContent'
            )
            or ''
        )
        index = trackinfo.find(' - ')

        if index > -1:
            track['artist'] = trackinfo[:index]
            track['title'] = trackinfo[index + 3:]
        else:
            # Might find some kind of title anyway in metadata
            track['title'] = metadata.findtext(
                './/{http://purl.org/dc/' 'elements/1.1/}title'
            )
            if not track['title']:
                track['title'] = trackinfo

    # If the speaker is playing from the line-in source, querying for track
    # metadata will return 'NOT_IMPLEMENTED'.
    elif metadata not in ('', 'NOT_IMPLEMENTED', None):
        # Track metadata is returned in DIDL-Lite format
        metadata = ElementTree.fromstring(metadata)
        md_title = metadata.findtext('.//{http://purl.org/dc/elements/1.1/}title')
        md_artist = metadata.findtext(
            './/{http://purl.org/dc/elements/1.1/}creator'
        )
        md_album = metadata.findtext(
            './/{urn:schemas-upnp-org:metadata-1-0/upnp/}album'
        )

        track['title'] = ''
        if md_title:
            track['title'] = md_title
        track['artist'] = ''
        if md_artist:
            track['artist'] = md_artist
        track['album'] = ''
        if md_album:
            track['album'] = md_album

        album_art_url = metadata.findtext(
            './/{urn:schemas-upnp-org:metadata-1-0/upnp/}albumArtURI'
        )
        if album_art_url is not None:
            # track['album_art'] = self.music_library.build_album_art_full_uri(
            #     album_art_url
            # )
            pass

    return track


async def get_transport_info(player: models.Player) -> Dict[str, Any]:
    '''Get the current playback state.

    Returns:
        dict: The following information about the
        speaker's playing state:

        *   state (``PLAYING``, ``TRANSITIONING``, ``PAUSED_PLAYBACK``, ``STOPPED``)
        *   status (OK, ?)
        *   speed(1, ?)

    This allows us to know if speaker is playing or not. Other values for
    status and speed are unknown.
    '''
    client = upnp.get_upnp_client(player)
    result = await client.send_command(
        upnp.SERVICE_AVTRANSPORT,
        'GetTransportInfo',
        [('InstanceID', 0)],
    )

    return {
        'state': result['CurrentTransportState'],
        'status': result['CurrentTransportStatus'],
        'speed': result['CurrentSpeed'],
    }


async def play(player: models.Player):
    '''Start playing the currently selected track on player.'''
    await _simple_avtransport_command(player, 'Play')


async def pause(player: models.Player):
    await _simple_avtransport_command(player, 'Pause')


async def stop(player: models.Player):
    await _simple_avtransport_command(player, 'Stop')


async def _simple_avtransport_command(player: models.Player, command: str):
    client = upnp.get_upnp_client(player)
    await client.send_command(
        upnp.SERVICE_AVTRANSPORT,
        command,
        [
            ('InstanceID', 0),
            ('Speed', 1),
        ],
    )


async def get_queue(
        player: models.Player,
        start=0,
        max_items=100,
        full_album_art_uri=False) -> models.TrackList:
    '''Get information about the queue.

    :param start: Starting number of returned matches
    :param max_items: Maximum number of returned matches
    :param full_album_art_uri: If the album art URI should include the
        IP address
    :returns: A :py:class:`~.models.Queue` object

    This method is heavily based on Sam Soffes (aka soffes) ruby
    implementation
    '''
    client = upnp.get_upnp_client(player)
    result = await client.send_command(
        upnp.SERVICE_CONTENT_DIRECTORY,
        'Browse',
        [
            ('ObjectID', 'Q:0'),
            ('BrowseFlag', 'BrowseDirectChildren'),
            ('Filter', '*'),
            ('StartingIndex', start),
            ('RequestedCount', max_items),
            ('SortCriteria', ''),
        ],
    )

    items = parsers.parse_didl(result['Result'])

    tracks: List[didl.MusicTrack] = []
    for item in items:
        if isinstance(item, didl.MusicTrack):
            tracks.append(item)

    return models.TrackList(
        tracks,
        int(result['NumberReturned']),
        int(result['TotalMatches']),
        result['UpdateID'],
    )


async def clear_queue(player: models.Player):
    client = upnp.get_upnp_client(player)
    result = await client.send_command(
        upnp.SERVICE_AVTRANSPORT,
        'RemoveAllTracksFromQueue',
        [
            ('InstanceID', 0),
        ],
    )
    log.debug('clear_queue: result = %r', result)


async def add_uri_to_queue(
        player: models.Player,
        uri: str,
        position=0,
        as_next=False):
    client = upnp.get_upnp_client(player)
    result = await client.send_command(
        upnp.SERVICE_AVTRANSPORT,
        'AddURIToQueue',
        [
            ('InstanceID', 0),
            ('EnqueuedURI', uri),
            ('EnqueuedURIMetaData', ''),     # must be present, otherwise ignored
            ('DesiredFirstTrackNumberEnqueued', position),
            ('EnqueueAsNext', int(as_next)),
        ],
    )
    log.debug('add_uri_to_queue: result = %r', result)


async def subscribe(
        player: models.Player,
        service: upnp.UPnPService,
        callback: event.EventCB,
        auto_renew: bool = False) -> event.Subscription:
    '''Subscribe to events from the specified UPnP service on one player.

    Every event results in a call to ``callback(event)``, where ``event``
    is an event.Event object.

    The events received are determined by the service and player that you
    subscribe to. For example, subscribing to upnp.SERVICE_AVTRANSPORT on
    player ``p`` will result in an event every time the play state of
    ``p`` changes: start playing, pause playing, stop playing, seek forward
    or backwards, or change track. Subscribing to upnp.SERVICE_TOPOLOGY on
    any player will result in an event every time the topology of your
    network changes. (Topology events are a bit special: all players
    publish the same topology events on every change, so there is no need
    to subscribe to more than one player.)
    '''
    sub = event.Subscription(upnp.get_session(), player, service, callback)
    await sub.subscribe(auto_renew=auto_renew)
    return sub


def get_subscriptions_for_player(player: models.Player) -> List[event.Subscription]:
    '''Return all subscriptions for the specified player.'''
    return event.Subscription.get_subscriptions(player)


async def close() -> None:
    '''Release any resources held by this library.'''
    await event.Subscription.unsubscribe_all()
    await upnp.close()


def parse_time(time_str: str) -> int:
    """convert a string of the form h:mm:ss to seconds"""
    if time_str == 'NOT_IMPLEMENTED':
        return -1
    bits = time_str.split(':')
    return int(bits[0]) * 3600 + int(bits[1]) * 60 + int(bits[2])
