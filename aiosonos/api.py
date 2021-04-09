import logging
from xml.etree import ElementTree
from typing import List

from . import models, upnp

log = logging.getLogger(__name__)


async def get_group_state(player: models.Player) -> models.Network:

    # # XXX SoCo caches both the raw XML and the parsed result: worth it?
    # now = time.monotonic()
    # if (self._group_state_update is not None and
    #         now - self._group_state_update <= self.group_state_ttl):
    #     return

    # if self._upnp_client is None:
    #     self._upnp_client = upnp.get_upnp_client(self.ip_address)

    client = upnp.get_upnp_client(player.ip_address)
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

    def parse_member(member_element) -> models.Player:
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
