import logging
from typing import Optional, ClassVar, Dict, List
from urllib import parse as urlparse

from didl_lite import didl_lite as didl

log = logging.getLogger(__name__)


def stdrepr(self):
    return '<{} at {:x}: {}>'.format(self.__class__.__name__, id(self), self)


class Player:
    _instances: ClassVar[Dict[str, 'Player']] = {}

    ip_address: str
    base_url: str
    uuid: Optional[str]
    name: Optional[str]
    is_coordinator: Optional[bool]
    is_bridge: Optional[bool]

    @classmethod
    def get_instance(cls, ip_address: str) -> 'Player':
        player = cls._instances.get(ip_address)
        if player is None:
            player = cls._instances[ip_address] = cls(ip_address)
        return player

    def __init__(self, ip_address: str):
        self.ip_address = ip_address
        self.base_url = 'http://{}:1400/'.format(self.ip_address)
        self.uuid = None
        self.name = None
        self.is_coordinator = None
        self.is_bridge = None

    def __eq__(self, other) -> bool:
        return (isinstance(other, self.__class__) and
                self.ip_address == other.ip_address)

    def __ne__(self, other) -> bool:
        return not self.__eq__(other)

    def __hash__(self) -> int:
        return hash(self.ip_address)

    def __str__(self) -> str:
        if self.uuid is None:
            return self.ip_address
        else:
            return '{}/{}'.format(self.ip_address, self.uuid)

    __repr__ = stdrepr

    def describe(self) -> str:
        return '{}: {}{}'.format(
            self,
            self.name,
            ' (coordinator)' if self.is_coordinator else '',
        )

    def get_url(self, path: str) -> str:
        return urlparse.urljoin(self.base_url, path)


class PlayerDescription:
    udn: str
    room_name: str
    display_name: str


class Group:
    uuid: str
    coordinator: Player
    members: List[Player]

    def __init__(
            self,
            uuid: str,
            coordinator: Player,
            members: List[Player]):
        self.uuid = uuid
        self.coordinator = coordinator
        self.members = members

    def __str__(self) -> str:
        return self.uuid

    __repr__ = stdrepr


class Network:                  # or is this a household?
    groups: List[Group]
    visible_players: List[Player]
    all_players: List[Player]

    def __init__(
            self,
            groups: List[Group],
            visible_players: List[Player],
            all_players: List[Player]):
        self.groups = groups
        self.visible_players = visible_players
        self.all_players = all_players

    def __str__(self) -> str:
        return '{} groups, {} players'.format(len(self.groups), len(self.all_players))

    __repr__ = stdrepr

    def get_coordinators(self) -> List[Player]:
        '''return the list of all group coordinators in the network'''
        return [group.coordinator for group in self.groups]

    def get_group(self, coordinator: Player) -> Optional[Group]:
        '''return the group with the specified coordinator (or None)'''
        for group in self.groups:
            if group.coordinator == coordinator:
                return group
        return None


class TrackList:
    '''A list of music tracks. Used for queues and search results.'''
    tracks: List[didl.MusicTrack]
    number_returned: int
    total_matches: int
    update_id: str

    def __init__(
            self,
            tracks: List[didl.MusicTrack],
            number_returned: int,
            total_matches: int,
            update_id: str):
        self.tracks = tracks
        self.number_returned = number_returned
        self.total_matches = total_matches
        self.update_id = update_id

    def __str__(self):
        return '{} tracks'.format(len(self.tracks))

    __repr__ = stdrepr

    def __iter__(self):
        return iter(self.tracks)

    def __len__(self):
        return len(self.tracks)
