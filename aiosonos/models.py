import logging
from typing import Optional, ClassVar, Dict, Set, List

log = logging.getLogger(__name__)


class Player:
    # group_state_ttl: ClassVar[float] = 5.0
    _instances: ClassVar[Dict[str, 'Player']] = {}

    ip_address: str
    uuid: Optional[str]
    name: Optional[str]
    is_coordinator: Optional[bool]
    is_bridge: Optional[bool]

    # _upnp_client: Optional[upnp.UPnPClient]
    # _group_state_update: float

    @classmethod
    def get_instance(cls, ip_address: str) -> 'Player':
        player = cls._instances.get(ip_address)
        if player is None:
            player = cls._instances[ip_address] = cls(ip_address)
        return player

    def __init__(self, ip_address: str):
        self.ip_address = ip_address
        self.uuid = None
        self.name = None
        self.is_coordinator = None
        self.is_bridge = None

        # self._upnp_client = None
        # self._group_state_update = 0.0

    # def __hash__(self):
    #     return hash(self.ip_address)

    # def __eq__(self, other):
    #     return (isinstance(other, type(self)) and
    #             self.ip_address == other.ip_address)

    # def __ne__(self, other):
    #     return not self.__eq__(other)

    def __str__(self):
        if self.uuid is None:
            return self.ip_address
        else:
            return '{}/{}'.format(self.ip_address, self.uuid)

    def __repr__(self):
        return '<{} at {:x}: {}>'.format(
            self.__class__.__name__, id(self), self)

    def describe(self):
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

    def __str__(self):
        return self.uuid

    def __repr__(self):
        return '<{} at {:x}: {}>'.format(
            self.__class__.__name__, id(self), self)

    # def __hash__(self):
    #     return hash(self.uuid) ^ hash(self.coordinator) ^ hash(self.members)

    # def __eq__(self, other):
    #     return (
    #         isinstance(other, type(self)) and
    #         self.uuid == other.uuid and
    #         self.coordinator == other.coordinator and
    #         self.members == other.members
    #     )

    # def __ne__(self, other):
    #     return not self.__eq__(other)


class Network:                  # or is this a household?
    groups: Set[Group]
    visible_players: Set[Player]
    all_players: Set[Player]

    def __init__(self, groups, visible_players, all_players):
        self.groups = groups
        self.visible_players = visible_players
        self.all_players = all_players
