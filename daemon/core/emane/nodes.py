"""
Provides an EMANE network node class, which has several attached NEMs that
share the same MAC+PHY model.
"""

import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, Type

from core.emulator.data import InterfaceData, LinkData, LinkOptions
from core.emulator.distributed import DistributedServer
from core.emulator.enumerations import (
    EventTypes,
    LinkTypes,
    MessageFlags,
    NodeTypes,
    RegisterTlvs,
)
from core.errors import CoreError
from core.nodes.base import CoreNetworkBase, CoreNode
from core.nodes.interface import CoreInterface

if TYPE_CHECKING:
    from core.emane.emanemodel import EmaneModel
    from core.emulator.session import Session
    from core.location.mobility import WirelessModel, WayPointMobility

    OptionalEmaneModel = Optional[EmaneModel]
    WirelessModelType = Type[WirelessModel]

try:
    from emane.events import LocationEvent
except ImportError:
    try:
        from emanesh.events import LocationEvent
    except ImportError:
        LocationEvent = None
        logging.debug("compatible emane python bindings not installed")


class EmaneNet(CoreNetworkBase):
    """
    EMANE node contains NEM configuration and causes connected nodes
    to have TAP interfaces (instead of VEth). These are managed by the
    Emane controller object that exists in a session.
    """

    apitype: NodeTypes = NodeTypes.EMANE
    linktype: LinkTypes = LinkTypes.WIRED
    type: str = "wlan"
    has_custom_iface: bool = True

    def __init__(
        self,
        session: "Session",
        _id: int = None,
        name: str = None,
        server: DistributedServer = None,
    ) -> None:
        super().__init__(session, _id, name, server)
        self.conf: str = ""
        self.model: "OptionalEmaneModel" = None
        self.mobility: Optional[WayPointMobility] = None

    def linkconfig(
        self, iface: CoreInterface, options: LinkOptions, iface2: CoreInterface = None
    ) -> None:
        """
        The CommEffect model supports link configuration.
        """
        if not self.model:
            return
        self.model.linkconfig(iface, options, iface2)

    def config(self, conf: str) -> None:
        self.conf = conf

    def startup(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def link(self, iface1: CoreInterface, iface2: CoreInterface) -> None:
        pass

    def unlink(self, iface1: CoreInterface, iface2: CoreInterface) -> None:
        pass

    def linknet(self, net: "CoreNetworkBase") -> CoreInterface:
        raise CoreError("emane networks cannot be linked to other networks")

    def updatemodel(self, config: Dict[str, str]) -> None:
        if not self.model:
            raise CoreError(f"no model set to update for node({self.name})")
        logging.info(
            "node(%s) updating model(%s): %s", self.id, self.model.name, config
        )
        self.model.update_config(config)

    def setmodel(self, model: "WirelessModelType", config: Dict[str, str]) -> None:
        """
        set the EmaneModel associated with this node
        """
        if model.config_type == RegisterTlvs.WIRELESS:
            # EmaneModel really uses values from ConfigurableManager
            #  when buildnemxml() is called, not during init()
            self.model = model(session=self.session, _id=self.id)
            self.model.update_config(config)
        elif model.config_type == RegisterTlvs.MOBILITY:
            self.mobility = model(session=self.session, _id=self.id)
            self.mobility.update_config(config)

    def _nem_position(
        self, iface: CoreInterface
    ) -> Optional[Tuple[int, float, float, float]]:
        """
        Creates nem position for emane event for a given interface.

        :param iface: interface to get nem emane position for
        :return: nem position tuple, None otherwise
        """
        nem_id = self.session.emane.get_nem_id(iface)
        ifname = iface.localname
        if nem_id is None:
            logging.info("nemid for %s is unknown", ifname)
            return
        node = iface.node
        x, y, z = node.getposition()
        lat, lon, alt = self.session.location.getgeo(x, y, z)
        # 使得读取到ns2移动脚本的z能够写入emane高度 而不是默认初始值
        # if node.position.alt is not None:
        #     alt = node.position.alt
        # logging.info("lon lat alt(%f %f %f)", lon, lat, alt)
        node.position.set_geo(lon, lat, alt)
        # altitude must be an integer or warning is printed
        alt = int(round(alt))
        return nem_id, lon, lat, alt

    def setnemposition(self, iface: CoreInterface) -> None:
        """
        Publish a NEM location change event using the EMANE event service.

        :param iface: interface to set nem position for
        """
        if self.session.emane.service is None:
            logging.info("position service not available")
            return
        position = self._nem_position(iface)
        if position:
            nemid, lon, lat, alt = position
            event = LocationEvent()
            event.append(nemid, latitude=lat, longitude=lon, altitude=alt)
            self.session.emane.service.publish(0, event)

    def setnempositions(self, moved_ifaces: List[CoreInterface]) -> None:
        """
        Several NEMs have moved, from e.g. a WaypointMobilityModel
        calculation. Generate an EMANE Location Event having several
        entries for each interface that has moved.
        """
        if len(moved_ifaces) == 0:
            return

        if self.session.emane.service is None:
            logging.info("position service not available")
            return

        event = LocationEvent()
        for iface in moved_ifaces:
            position = self._nem_position(iface)
            if position:
                nemid, lon, lat, alt = position
                event.append(nemid, latitude=lat, longitude=lon, altitude=alt)
        self.session.emane.service.publish(0, event)

    def links(self, flags: MessageFlags = MessageFlags.NONE) -> List[LinkData]:
        links = super().links(flags)
        emane_manager = self.session.emane
        # gather current emane links
        nem_ids = set()
        for iface in self.get_ifaces():
            nem_id = emane_manager.get_nem_id(iface)
            nem_ids.add(nem_id)
        emane_links = emane_manager.link_monitor.links
        considered = set()
        # for link_key in emane_links.copy(): # 似乎某些情况下emane_links字典会在遍历下修改 造成迭代器失效
        for link_key in emane_links:
            considered_key = tuple(sorted(link_key))
            if considered_key in considered:
                continue
            considered.add(considered_key)
            nem1, nem2 = considered_key
            # ignore links not related to this node
            if nem1 not in nem_ids and nem2 not in nem_ids:
                continue
            # ignore incomplete links
            if (nem2, nem1) not in emane_links:
                continue
            link = emane_manager.get_nem_link(nem1, nem2)
            if link:
                links.append(link)
        return links

    def custom_iface(self, node: CoreNode, iface_data: InterfaceData) -> CoreInterface:
        # TUN/TAP is not ready for addressing yet; the device may
        #   take some time to appear, and installing it into a
        #   namespace after it has been bound removes addressing;
        #   save addresses with the interface now
        iface_id = node.newtuntap(iface_data.id, iface_data.name)
        node.attachnet(iface_id, self)
        iface = node.get_iface(iface_id)
        iface.set_mac(iface_data.mac)
        for ip in iface_data.get_ips():
            iface.add_ip(ip)
        if self.session.state == EventTypes.RUNTIME_STATE:
            self.session.emane.start_iface(self, iface)
        return iface
