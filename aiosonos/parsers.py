'''parse Sonos XML and turn it into useful model objects'''

import logging
from xml.etree import ElementTree
from typing import Union, Any, Dict, List

from . import utils, models, didl, errors

log = logging.getLogger(__name__)


def parse_group_state(groups_xml: str) -> models.Network:
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


def parse_event_body(body: bytes) -> Dict[str, Any]:
    '''Parse the body of a UPnP event.

    Args:
        body (bytes): bytes containing the body of the event encoded
            with utf-8.

    Returns:
        dict: A dict with keys representing the evented variables. The
        relevant value will usually be a string representation of the
        variable's value, but may on occasion be:

        * a dict (eg when the volume changes, the value will itself be a
          dict containing the volume for each channel:
          :code:`{'Volume': {'LF': '100', 'RF': '100', 'Master': '36'}}`)
        * an instance of a `DidlObject` subclass (eg if it represents
          track metadata).
        * a `SoCoFault` (if a variable contains illegal metadata)
    '''

    result = {}
    tree = ElementTree.fromstring(body)
    # property values are just under the propertyset, which
    # uses this namespace
    properties = tree.findall('{urn:schemas-upnp-org:event-1-0}property')
    for prop in properties:
        for variable in prop:
            # Special handling for a LastChange event specially. For details on
            # LastChange events, see
            # http://upnp.org/specs/av/UPnP-av-RenderingControl-v1-Service.pdf
            # and http://upnp.org/specs/av/UPnP-av-AVTransport-v1-Service.pdf
            if variable.tag == 'LastChange':
                assert variable.text is not None, '<LastChange> element with no text'
                result.update(parse_last_change(variable.text))
            elif variable.tag == 'ZoneGroupState':
                assert variable.text is not None, '<ZoneGroupState> element with no text'
                result[variable.tag] = parse_group_state(variable.text)
            else:
                result[variable.tag] = variable.text
            # result[variable.tag] = variable.text

    return result


def parse_last_change(text: str) -> Dict[str, Any]:
    '''Parse a <LastChange> event and return a generic dict.

    <LastChange> events seem to come from transport, queue, or rendering
    services, and they look quite different in each case.
    '''
    tree = ElementTree.fromstring(text)
    # We assume there is only one InstanceID tag. This is true for
    # Sonos, as far as we know.
    # InstanceID can be in one of two namespaces, depending on
    # whether we are looking at an avTransport event, a
    # renderingControl event, or a Queue event
    # (there, it is named QueueID)
    paths = [
        '{urn:schemas-upnp-org:metadata-1-0/AVT/}InstanceID',
        '{urn:schemas-upnp-org:metadata-1-0/RCS/}InstanceID',
        '{urn:schemas-sonos-com:metadata-1-0/Queue/}QueueID',
    ]
    for path in paths:
        instance = tree.find(path)
        if instance is not None:
            break
    assert instance is not None, \
        'could not find InstanceID or QueueID in <LastChange> element'

    # Look at each variable within the LastChange event
    result: Dict[str, Any] = {}
    for variable in instance:
        tag = variable.tag
        # Remove any namespaces from the tags
        if tag.startswith('{'):
            tag = tag.split('}', 1)[1]

        # Now extract the relevant value for the variable.
        # The UPnP specs suggest that the value of any variable
        # evented via a LastChange Event will be in the 'val'
        # attribute, but audio related variables may also have a
        # 'channel' attribute. In addition, it seems that Sonos
        # sometimes uses a text value instead: see
        # http://forums.sonos.com/showthread.php?t=34663
        value: Union[None, str, didl.DIDLObject]
        value = variable.get('val')
        if value is None:
            value = variable.text
        assert value is not None

        # If DIDL metadata is returned, convert it to a music
        # library data structure (disabled for now!)
        if value.startswith('<DIDL-Lite'):
            value = parse_didl(value)[0]
        channel = variable.get('channel')
        if channel is not None:
            if result.get(tag) is None:
                result[tag] = {}
            result[tag][channel] = value
        else:
            result[tag] = value

    return result


def parse_didl(didl_xml: str) -> List[didl.DIDLObject]:
    '''Parse an XML representation of DIDL (Digital Item Declaration Language) items

    Args:
        string (str): A unicode string containing an XML representation of one
            or more DIDL-Lite items (in the form  ``'<DIDL-Lite ...>
            ...</DIDL-Lite>'``)

    Returns:
        list: A list of one or more instances of `DIDLObject` or a subclass
    '''
    items = []
    root = ElementTree.fromstring(didl_xml)
    for elt in root:
        if elt.tag.endswith('item') or elt.tag.endswith('container'):
            item_class = elt.findtext(utils.ns_tag('upnp', 'class'))
            assert item_class is not None, 'no item class found in %s' % (elt,)
            cls = didl.get_didl_class(item_class)
            item = cls.from_element(elt)
            items.append(item)
        else:
            # <desc> elements are allowed as an immediate child of <DIDL-Lite>
            # according to the spec, but I have not seen one there in Sonos, so
            # we treat them as illegal. May need to fix this if this
            # causes problems.
            raise errors.DIDLMetadataError(
                'Illegal child of DIDL element: <%s>' % elt.tag)
    return items