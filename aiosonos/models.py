import logging
from typing import Optional, ClassVar, Dict, List

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
