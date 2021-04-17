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

from . import models, upnp, discover, event

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
    return _parse_group_state(groups_xml)


def _parse_group_state(groups_xml: str) -> models.Network:
    """
    :return: (groups, visible_players, all_players)
    """
    # GetZoneGroupState returns XML like this:
    #
    # <ZoneGroups>
    #   <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000XXXX1400:0">
    #     <ZoneGroupMember
    #         BootSeq="33"
    #         Configuration="1"
    #         Icon="x-rincon-roomicon:zoneextender"
    #         Invisible="1"
    #         IsZoneBridge="1"
    #         Location="http://192.168.1.100:1400/xml/device_description.xml"
    #         MinCompatibleVersion="22.0-00000"
    #         SoftwareVersion="24.1-74200"
    #         UUID="RINCON_000ZZZ1400"
    #         ZoneName="BRIDGE"/>
    #   </ZoneGroup>
    #   <ZoneGroup Coordinator="RINCON_000XXX1400" ID="RINCON_000XXX1400:46">
    #     <ZoneGroupMember
    #         BootSeq="44"
    #         Configuration="1"
    #         Icon="x-rincon-roomicon:living"
    #         Location="http://192.168.1.101:1400/xml/device_description.xml"
    #         MinCompatibleVersion="22.0-00000"
    #         SoftwareVersion="24.1-74200"
    #         UUID="RINCON_000XXX1400"
    #         ZoneName="Living Room"/>
    #     <ZoneGroupMember
    #         BootSeq="52"
    #         Configuration="1"
    #         Icon="x-rincon-roomicon:kitchen"
    #         Location="http://192.168.1.102:1400/xml/device_description.xml"
    #         MinCompatibleVersion="22.0-00000"
    #         SoftwareVersion="24.1-74200"
    #         UUID="RINCON_000YYY1400"
    #         ZoneName="Kitchen"/>
    #   </ZoneGroup>
    # </ZoneGroups>
    #

    groups = list()
    visible_players = list()
    all_players = list()

    def parse_member(member_element: ElementTree.Element) -> models.Player:
        """Parse a ZoneGroupMember or Satellite element from Zone Group
        State, create a SoCo instance for the member, set basic attributes
        and return it."""
        # Get (or create) the Player instance for each member. This is
        # cheap if they have already been created, and useful if they
        # haven't. We can then update various properties for that
        # instance.
        member_attribs = member_element.attrib
        ip_addr = member_attribs["Location"].split("//")[1].split(":")[0]
        player = models.Player.get_instance(ip_addr)
        # uid doesn't change, but it's not harmful to (re)set it, in case
        # the player is as yet unseen.
        player.uuid = member_attribs["UUID"]
        player.name = member_attribs["ZoneName"]
        # add the player to the set of all members, and to the set
        # of visible members if appropriate
        is_visible = member_attribs.get("Invisible") != "1"
        if is_visible:
            visible_players.append(player)
        all_players.append(player)
        return player

    tree = ElementTree.fromstring(groups_xml)

    # Loop over each ZoneGroup Element
    zg_element = tree.find('ZoneGroups')
    assert zg_element is not None, 'no ZoneGroups element'
    for group_element in zg_element.findall("ZoneGroup"):
        coordinator_uuid = group_element.attrib["Coordinator"]
        group_uuid = group_element.attrib["ID"]
        group_coordinator = None
        members: List[models.Player] = list()
        for member_element in group_element.findall("ZoneGroupMember"):
            player = parse_member(member_element)
            # Perform extra processing relevant to direct zone group
            # members
            #
            # If this element has the same UUID as the coordinator, it is
            # the coordinator
            if player.uuid == coordinator_uuid:
                group_coordinator = player
                player.is_coordinator = True
            else:
                player.is_coordinator = False
            # is_bridge doesn't change, but it does no real harm to
            # set/reset it here, just in case the player has not been seen
            # before
            player.is_bridge = member_element.attrib.get("IsZoneBridge") == "1"
            # add the player to the members for this group
            members.append(player)
            # Loop over Satellite elements if present, and process as for
            # ZoneGroup elements
            for satellite_element in member_element.findall("Satellite"):
                player = parse_member(satellite_element)
                # Assume a satellite can't be a bridge or coordinator, so
                # no need to check.
                #
                # Add the player to the members for this group.
                members.append(player)
            # Now create a Group with this info and add it to the list
            # of groups
        assert group_coordinator is not None, 'found group with no coordinator'
        groups.append(models.Group(group_uuid, group_coordinator, members))

    return models.Network(groups, visible_players, all_players)


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


async def subscribe(
        player: models.Player,
        service: upnp.UPnPService,
        callback: event.EventCB) -> event.Subscription:
    sub = event.Subscription(upnp.get_session(), player, service, callback)
    await sub.subscribe()
    return sub


async def close() -> None:
    '''Release any resources held by this library.'''
    await upnp.close()
