"""
Incorporate grpc into python tkinter GUI
"""
import getpass
import json
import logging
import os
import tkinter as tk
from tkinter import messagebox
from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Set, Tuple

import grpc

from core.api.grpc import (
    client,
    configservices_pb2,
    core_pb2,
    emane_pb2,
    mobility_pb2,
    services_pb2,
    wlan_pb2,
)
from core.api.grpc.wrappers import (
    ConfigOption,
    ConfigService,
    ExceptionEvent,
    Link,
    LinkEvent,
    LinkType,
    MessageType,
    Node,
    NodeEvent,
    NodeServiceData,
    NodeType,
    Position,
    Session,
    SessionLocation,
    SessionState,
    ThroughputsEvent,
)
from core.gui import nodeutils as nutils
from core.gui.appconfig import XMLS_PATH, CoreServer, Observer
from core.gui.dialogs.emaneinstall import EmaneInstallDialog
from core.gui.dialogs.mobilityplayer import MobilityPlayer
from core.gui.dialogs.sessions import SessionsDialog
from core.gui.graph.edges import CanvasEdge
from core.gui.graph.node import CanvasNode
from core.gui.graph.shape import Shape
from core.gui.interface import InterfaceManager
from core.gui.nodeutils import NodeDraw

if TYPE_CHECKING:
    from core.gui.app import Application

GUI_SOURCE = "gui"
CPU_USAGE_DELAY = 3


def to_dict(config: Dict[str, ConfigOption]) -> Dict[str, str]:
    return {x: y.value for x, y in config.items()}


class CoreClient:
    def __init__(self, app: "Application", proxy: bool) -> None:
        """
        Create a CoreGrpc instance
        """
        self.app: "Application" = app
        self.master: tk.Tk = app.master
        self._client: client.CoreGrpcClient = client.CoreGrpcClient(proxy=proxy)
        self.session: Optional[Session] = None
        self.user = getpass.getuser()

        # global service settings
        self.services: Dict[str, Set[str]] = {}
        self.config_services_groups: Dict[str, Set[str]] = {}
        self.config_services: Dict[str, ConfigService] = {}

        # loaded configuration data
        self.servers: Dict[str, CoreServer] = {}
        self.custom_nodes: Dict[str, NodeDraw] = {}
        self.custom_observers: Dict[str, Observer] = {}
        self.read_config()

        # helpers
        self.iface_to_edge: Dict[Tuple[int, ...], CanvasEdge] = {}
        self.ifaces_manager: InterfaceManager = InterfaceManager(self.app)
        self.observer: Optional[str] = None

        # session data
        self.mobility_players: Dict[int, MobilityPlayer] = {}
        self.canvas_nodes: Dict[int, CanvasNode] = {}
        self.links: Dict[str, CanvasEdge] = {}
        self.handling_throughputs: Optional[grpc.Future] = None
        self.handling_cpu_usage: Optional[grpc.Future] = None
        self.handling_events: Optional[grpc.Future] = None

    @property
    def client(self) -> client.CoreGrpcClient:
        if self.session:
            response = self._client.check_session(self.session.id)
            if not response.result:
                throughputs_enabled = self.handling_throughputs is not None
                self.cancel_throughputs()
                self.cancel_events()
                self._client.create_session(self.session.id)
                self.handling_events = self._client.events(
                    self.session.id, self.handle_events
                )
                if throughputs_enabled:
                    self.enable_throughputs()
            self.setup_cpu_usage()
        return self._client

    def set_canvas_node(self, node: Node, canvas_node: CanvasNode) -> None:
        self.canvas_nodes[node.id] = canvas_node

    def get_canvas_node(self, node_id: int) -> CanvasNode:
        return self.canvas_nodes[node_id]

    def reset(self) -> None:
        # helpers
        self.ifaces_manager.reset()
        self.iface_to_edge.clear()
        # session data
        self.canvas_nodes.clear()
        self.links.clear()
        self.close_mobility_players()
        self.mobility_players.clear()
        # clear streams
        self.cancel_throughputs()
        self.cancel_events()

    def close_mobility_players(self) -> None:
        for mobility_player in self.mobility_players.values():
            mobility_player.close()

    def set_observer(self, value: Optional[str]) -> None:
        self.observer = value

    def read_config(self) -> None:
        # read distributed servers
        for server in self.app.guiconfig.servers:
            self.servers[server.name] = server
        # read custom nodes
        for custom_node in self.app.guiconfig.nodes:
            node_draw = NodeDraw.from_custom(custom_node)
            self.custom_nodes[custom_node.name] = node_draw
        # read observers
        for observer in self.app.guiconfig.observers:
            self.custom_observers[observer.name] = observer

    def handle_events(self, event: core_pb2.Event) -> None:
        if not self.session or event.source == GUI_SOURCE:
            return
        if event.session_id != self.session.id:
            logging.warning(
                "ignoring event session(%s) current(%s)",
                event.session_id,
                self.session.id,
            )
            return

        if event.HasField("link_event"):
            link_event = LinkEvent.from_proto(event.link_event)
            self.app.after(0, self.handle_link_event, link_event)
        elif event.HasField("session_event"):
            logging.info("session event: %s", event)
            session_event = event.session_event
            if session_event.event <= SessionState.SHUTDOWN.value:
                self.session.state = SessionState(session_event.event)
            elif session_event.event in {7, 8, 9}:
                node_id = session_event.node_id
                dialog = self.mobility_players.get(node_id)
                if dialog:
                    if session_event.event == 7:
                        dialog.set_play()
                    elif session_event.event == 8:
                        dialog.set_stop()
                    else:
                        dialog.set_pause()
            else:
                logging.warning("unknown session event: %s", session_event)
        elif event.HasField("node_event"):
            node_event = NodeEvent.from_proto(event.node_event)
            self.app.after(0, self.handle_node_event, node_event)
        elif event.HasField("config_event"):
            logging.info("config event: %s", event)
        elif event.HasField("exception_event"):
            event = ExceptionEvent.from_proto(event.session_id, event.exception_event)
            self.handle_exception_event(event)
        else:
            logging.info("unhandled event: %s", event)

    def handle_link_event(self, event: LinkEvent) -> None:
        logging.debug("Link event: %s", event)
        node1_id = event.link.node1_id
        node2_id = event.link.node2_id
        if node1_id == node2_id:
            logging.warning("ignoring links with loops: %s", event)
            return
        canvas_node1 = self.canvas_nodes[node1_id]
        canvas_node2 = self.canvas_nodes[node2_id]
        if event.link.type == LinkType.WIRELESS:
            if event.message_type == MessageType.ADD:
                self.app.manager.add_wireless_edge(
                    canvas_node1, canvas_node2, event.link
                )
            elif event.message_type == MessageType.DELETE:
                self.app.manager.delete_wireless_edge(
                    canvas_node1, canvas_node2, event.link
                )
            elif event.message_type == MessageType.NONE:
                self.app.manager.update_wireless_edge(
                    canvas_node1, canvas_node2, event.link
                )
            else:
                logging.warning("unknown link event: %s", event)
        else:
            if event.message_type == MessageType.ADD:
                self.app.manager.add_wired_edge(canvas_node1, canvas_node2, event.link)
            elif event.message_type == MessageType.DELETE:
                self.app.manager.delete_wired_edge(event.link)
            elif event.message_type == MessageType.NONE:
                self.app.manager.update_wired_edge(event.link)
            else:
                logging.warning("unknown link event: %s", event)

    def handle_node_event(self, event: NodeEvent) -> None:
        logging.debug("node event: %s", event)
        node = event.node
        if event.message_type == MessageType.NONE:
            canvas_node = self.canvas_nodes[node.id]
            x = node.position.x
            y = node.position.y
            canvas_node.move(x, y)
            if node.icon and node.icon != canvas_node.core_node.icon:
                canvas_node.update_icon(node.icon)
        elif event.message_type == MessageType.DELETE:
            canvas_node = self.canvas_nodes[node.id]
            canvas_node.canvas.clear_selection()
            canvas_node.canvas.select_object(canvas_node.id)
            canvas_node.canvas.delete_selected_objects()
        elif event.message_type == MessageType.ADD:
            if node.id in self.session.nodes:
                logging.error("core node already exists: %s", node)
            self.app.manager.add_core_node(node)
        else:
            logging.warning("unknown node event: %s", event)

    def enable_throughputs(self) -> None:
        self.handling_throughputs = self.client.throughputs(
            self.session.id, self.handle_throughputs
        )

    def cancel_throughputs(self) -> None:
        if self.handling_throughputs:
            self.handling_throughputs.cancel()
            self.handling_throughputs = None
            self.app.manager.clear_throughputs()

    def cancel_events(self) -> None:
        if self.handling_events:
            self.handling_events.cancel()
            self.handling_events = None

    def cancel_cpu_usage(self) -> None:
        if self.handling_cpu_usage:
            self.handling_cpu_usage.cancel()
            self.handling_cpu_usage = None

    def setup_cpu_usage(self) -> None:
        if self.handling_cpu_usage and self.handling_cpu_usage.running():
            return
        if self.handling_cpu_usage:
            self.handling_cpu_usage.cancel()
        self.handling_cpu_usage = self._client.cpu_usage(
            CPU_USAGE_DELAY, self.handle_cpu_event
        )

    def handle_throughputs(self, event: core_pb2.ThroughputsEvent) -> None:
        event = ThroughputsEvent.from_proto(event)
        if event.session_id != self.session.id:
            logging.warning(
                "ignoring throughput event session(%s) current(%s)",
                event.session_id,
                self.session.id,
            )
            return
        logging.debug("handling throughputs event: %s", event)
        self.app.after(0, self.app.manager.set_throughputs, event)

    def handle_cpu_event(self, event: core_pb2.CpuUsageEvent) -> None:
        self.app.after(0, self.app.statusbar.set_cpu, event.usage)

    def handle_exception_event(self, event: ExceptionEvent) -> None:
        logging.info("exception event: %s", event)
        self.app.statusbar.add_alert(event)

    def join_session(self, session_id: int) -> None:
        logging.info("joining session(%s)", session_id)
        self.reset()
        try:
            response = self.client.get_session(session_id)
            self.session = Session.from_proto(response.session)
            self.client.set_session_user(self.session.id, self.user)
            title_file = self.session.file.name if self.session.file else ""
            self.master.title(f"CORE Session({self.session.id}) {title_file}")
            self.handling_events = self.client.events(
                self.session.id, self.handle_events
            )
            self.ifaces_manager.joined(self.session.links)
            self.app.manager.join(self.session)
            if self.is_runtime():
                self.show_mobility_players()
            self.app.after(0, self.app.joined_session_update)
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Join Session Error", e)

    def is_runtime(self) -> bool:
        return self.session and self.session.state == SessionState.RUNTIME

    def parse_metadata(self) -> None:
        # canvas setting
        config = self.session.metadata
        canvas_config = config.get("canvas")
        logging.debug("canvas metadata: %s", canvas_config)
        if canvas_config:
            canvas_config = json.loads(canvas_config)
            self.app.manager.parse_metadata(canvas_config)

        # load saved shapes
        shapes_config = config.get("shapes")
        if shapes_config:
            shapes_config = json.loads(shapes_config)
            for shape_config in shapes_config:
                logging.debug("loading shape: %s", shape_config)
                Shape.from_metadata(self.app, shape_config)

        # load edges config
        edges_config = config.get("edges")
        if edges_config:
            edges_config = json.loads(edges_config)
            logging.info("edges config: %s", edges_config)
            for edge_config in edges_config:
                edge = self.links[edge_config["token"]]
                edge.width = edge_config["width"]
                edge.color = edge_config["color"]
                edge.redraw()

        # read hidden nodes
        hidden = config.get("hidden")
        if hidden:
            hidden = json.loads(hidden)
            for _id in hidden:
                canvas_node = self.canvas_nodes.get(_id)
                if canvas_node:
                    canvas_node.hide()
                else:
                    logging.warning("invalid node to hide: %s", _id)

    def create_new_session(self) -> None:
        """
        Create a new session
        """
        try:
            response = self.client.create_session()
            logging.info("created session: %s", response)
            self.join_session(response.session_id)
            location_config = self.app.guiconfig.location
            self.session.location = SessionLocation(
                x=location_config.x,
                y=location_config.y,
                z=location_config.z,
                lat=location_config.lat,
                lon=location_config.lon,
                alt=location_config.alt,
                scale=location_config.scale,
            )
        except grpc.RpcError as e:
            self.app.show_grpc_exception("New Session Error", e)

    def delete_session(self, session_id: int = None) -> None:
        if session_id is None and not self.session:
            return
        if session_id is None:
            session_id = self.session.id
        try:
            response = self.client.delete_session(session_id)
            logging.info("deleted session(%s), Result: %s", session_id, response)
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Delete Session Error", e)

    def setup(self, session_id: int = None) -> None:
        """
        Query sessions, if there exist any, prompt whether to join one
        """
        try:
            self.client.connect()
            # get all available services
            response = self.client.get_services()
            for service in response.services:
                group_services = self.services.setdefault(service.group, set())
                group_services.add(service.name)
            # get config service informations
            response = self.client.get_config_services()
            for service in response.services:
                self.config_services[service.name] = ConfigService.from_proto(service)
                group_services = self.config_services_groups.setdefault(
                    service.group, set()
                )
                group_services.add(service.name)
            # join provided session, create new session, or show dialog to select an
            # existing session
            response = self.client.get_sessions()
            sessions = response.sessions
            if session_id:
                session_ids = set(x.id for x in sessions)
                if session_id not in session_ids:
                    self.app.show_error(
                        "Join Session Error",
                        f"{session_id} does not exist",
                        blocking=True,
                    )
                    self.app.close()
                else:
                    self.join_session(session_id)
            else:
                if not sessions:
                    self.create_new_session()
                else:
                    dialog = SessionsDialog(self.app, True)
                    dialog.show()
        except grpc.RpcError as e:
            logging.exception("core setup error")
            self.app.show_grpc_exception("Setup Error", e, blocking=True)
            self.app.close()

    def edit_node(self, core_node: Node) -> None:
        try:
            position = core_node.position.to_proto()
            self.client.edit_node(
                self.session.id, core_node.id, position, source=GUI_SOURCE
            )
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Edit Node Error", e)

    def send_servers(self, dis_server: Set[str] = None) -> None:
        # 修复原有的初始化会话 会将未使用的分布式服务器传入后台实例化 的问题
        # for server in self.servers.values():
        # self.client.add_session_server(self.session.id, server.name, server.address)
        for s in dis_server:
            self.client.add_session_server(self.session.id, s, self.servers[s].address)

    def start_session(self) -> Tuple[bool, List[str]]:
        self.ifaces_manager.set_macs([x.link for x in self.links.values()])
        nodes = [x.to_proto() for x in self.session.nodes.values()]
        dis_server = set()
        for node in nodes:
            if node.server:
                dis_server.add(node.server)
        links = []
        asymmetric_links = []
        for edge in self.links.values():
            link = edge.link
            if link.iface1 and not link.iface1.mac:
                link.iface1.mac = self.ifaces_manager.next_mac()
            if link.iface2 and not link.iface2.mac:
                link.iface2.mac = self.ifaces_manager.next_mac()
            links.append(link.to_proto())
            if edge.asymmetric_link:
                asymmetric_links.append(edge.asymmetric_link.to_proto())
        wlan_configs = self.get_wlan_configs_proto()
        mobility_configs = self.get_mobility_configs_proto()
        emane_model_configs = self.get_emane_model_configs_proto()
        hooks = [x.to_proto() for x in self.session.hooks.values()]
        service_configs = self.get_service_configs_proto()
        file_configs = self.get_service_file_configs_proto()
        config_service_configs = self.get_config_service_configs_proto()
        emane_config = to_dict(self.session.emane_config)
        result = False
        exceptions = []
        try:
            self.send_servers(dis_server)
            response = self.client.start_session(
                self.session.id,
                nodes,
                links,
                self.session.location.to_proto(),
                hooks,
                emane_config,
                emane_model_configs,
                wlan_configs,
                mobility_configs,
                service_configs,
                file_configs,
                asymmetric_links,
                config_service_configs,
            )
            logging.info(
                "start session(%s), result: %s", self.session.id, response.result
            )
            if response.result:
                self.set_metadata()
            result = response.result
            exceptions = response.exceptions
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Start Session Error", e)
        return result, exceptions

    def stop_session(self, session_id: int = None) -> bool:
        if not session_id:
            session_id = self.session.id
        result = False
        try:
            response = self.client.stop_session(session_id)
            logging.info("stopped session(%s), result: %s", session_id, response)
            result = response.result
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Stop Session Error", e)
        return result

    def show_mobility_players(self) -> None:
        for node in self.session.nodes.values():
            if not nutils.is_mobility(node):
                continue
            if node.mobility_config:
                mobility_player = MobilityPlayer(self.app, node)
                self.mobility_players[node.id] = mobility_player
                mobility_player.show()

    def set_metadata(self) -> None:
        # create canvas data
        canvas_config = self.app.manager.get_metadata()
        canvas_config = json.dumps(canvas_config)

        # create shapes data
        shapes = []
        for canvas in self.app.manager.all():
            for shape in canvas.shapes.values():
                shapes.append(shape.metadata())
        shapes = json.dumps(shapes)

        # create edges config
        edges_config = []
        for edge in self.links.values():
            if not edge.is_customized():
                continue
            edge_config = dict(token=edge.token, width=edge.width, color=edge.color)
            edges_config.append(edge_config)
        edges_config = json.dumps(edges_config)

        # create hidden metadata
        hidden = [x.core_node.id for x in self.canvas_nodes.values() if x.hidden]
        hidden = json.dumps(hidden)

        # save metadata
        metadata = dict(
            canvas=canvas_config, shapes=shapes, edges=edges_config, hidden=hidden
        )
        response = self.client.set_session_metadata(self.session.id, metadata)
        logging.debug("set session metadata %s, result: %s", metadata, response)

    def launch_terminal(self, node_id: int) -> None:
        try:
            terminal = self.app.guiconfig.preferences.terminal
            if not terminal:
                messagebox.showerror(
                    "Terminal Error",
                    "No terminal set, please set within the preferences menu",
                    parent=self.app,
                )
                return
            response = self.client.get_node_terminal(self.session.id, node_id)
            cmd = f"{terminal} {response.terminal} &"
            logging.info("launching terminal %s", cmd)
            os.system(cmd)
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Node Terminal Error", e)

    def get_xml_dir(self) -> str:
        return str(self.session.file.parent) if self.session.file else str(XMLS_PATH)

    def save_xml(self, file_path: str = None) -> None:
        """
        Save core session as to an xml file
        """
        if not file_path and not self.session.file:
            logging.error("trying to save xml for session with no file")
            return
        if not file_path:
            file_path = str(self.session.file)
        try:
            if not self.is_runtime():
                logging.debug("Send session data to the daemon")
                self.send_data()
            response = self.client.save_xml(self.session.id, file_path)
            logging.info("saved xml file %s, result: %s", file_path, response)
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Save XML Error", e)

    def open_xml(self, file_path: str) -> None:
        """
        Open core xml
        """
        try:
            response = self._client.open_xml(file_path)
            logging.info("open xml file %s, response: %s", file_path, response)
            self.join_session(response.session_id)
        except grpc.RpcError as e:
            self.app.show_grpc_exception("Open XML Error", e)

    def get_node_service(self, node_id: int, service_name: str) -> NodeServiceData:
        response = self.client.get_node_service(self.session.id, node_id, service_name)
        logging.debug(
            "get node(%s) %s service, response: %s", node_id, service_name, response
        )
        return NodeServiceData.from_proto(response.service)

    def set_node_service(
        self,
        node_id: int,
        service_name: str,
        dirs: List[str],
        files: List[str],
        startups: List[str],
        validations: List[str],
        shutdowns: List[str],
    ) -> NodeServiceData:
        response = self.client.set_node_service(
            self.session.id,
            node_id,
            service_name,
            directories=dirs,
            files=files,
            startup=startups,
            validate=validations,
            shutdown=shutdowns,
        )
        logging.info(
            "Set %s service for node(%s), files: %s, Startup: %s, "
            "Validation: %s, Shutdown: %s, Result: %s",
            service_name,
            node_id,
            files,
            startups,
            validations,
            shutdowns,
            response,
        )
        response = self.client.get_node_service(self.session.id, node_id, service_name)
        return NodeServiceData.from_proto(response.service)

    def get_node_service_file(
        self, node_id: int, service_name: str, file_name: str
    ) -> str:
        response = self.client.get_node_service_file(
            self.session.id, node_id, service_name, file_name
        )
        logging.debug(
            "get service file for node(%s), service: %s, file: %s, result: %s",
            node_id,
            service_name,
            file_name,
            response,
        )
        return response.data

    def set_node_service_file(
        self, node_id: int, service_name: str, file_name: str, data: str
    ) -> None:
        response = self.client.set_node_service_file(
            self.session.id, node_id, service_name, file_name, data
        )
        logging.info(
            "set node(%s) service file, service: %s, file: %s, data: %s, result: %s",
            node_id,
            service_name,
            file_name,
            data,
            response,
        )

    def create_nodes_and_links(self) -> None:
        """
        create nodes and links that have not been created yet
        """
        self.client.set_session_state(self.session.id, SessionState.DEFINITION.value)
        for node in self.session.nodes.values():
            response = self.client.add_node(
                self.session.id, node.to_proto(), source=GUI_SOURCE
            )
            logging.debug("created node: %s", response)
        asymmetric_links = []
        for edge in self.links.values():
            self.add_link(edge.link)
            if edge.asymmetric_link:
                asymmetric_links.append(edge.asymmetric_link)
        for link in asymmetric_links:
            self.add_link(link)

    def send_data(self) -> None:
        """
        Send to daemon all session info, but don't start the session
        """
        self.send_servers()
        self.create_nodes_and_links()
        for config_proto in self.get_wlan_configs_proto():
            self.client.set_wlan_config(
                self.session.id, config_proto.node_id, config_proto.config
            )
        for config_proto in self.get_mobility_configs_proto():
            self.client.set_mobility_config(
                self.session.id, config_proto.node_id, config_proto.config
            )
        for config_proto in self.get_service_configs_proto():
            self.client.set_node_service(
                self.session.id,
                config_proto.node_id,
                config_proto.service,
                config_proto.files,
                config_proto.directories,
                config_proto.startup,
                config_proto.validate,
                config_proto.shutdown,
            )
        for config_proto in self.get_service_file_configs_proto():
            self.client.set_node_service_file(
                self.session.id,
                config_proto.node_id,
                config_proto.service,
                config_proto.file,
                config_proto.data,
            )
        for hook in self.session.hooks.values():
            self.client.add_hook(
                self.session.id, hook.state.value, hook.file, hook.data
            )
        for config_proto in self.get_emane_model_configs_proto():
            self.client.set_emane_model_config(
                self.session.id,
                config_proto.node_id,
                config_proto.model,
                config_proto.config,
                config_proto.iface_id,
            )
        config = to_dict(self.session.emane_config)
        self.client.set_emane_config(self.session.id, config)
        location = self.session.location
        self.client.set_session_location(
            self.session.id,
            location.x,
            location.y,
            location.z,
            location.lat,
            location.lon,
            location.alt,
            location.scale,
        )
        self.set_metadata()

    def close(self) -> None:
        """
        Clean ups when done using grpc
        """
        logging.debug("close grpc")
        self.client.close()

    def next_node_id(self) -> int:
        """
        Get the next usable node id.
        """
        i = 1
        while True:
            if i not in self.session.nodes:
                break
            i += 1
        return i

    def create_node(
        self, x: float, y: float, node_type: NodeType, model: str
    ) -> Optional[Node]:
        """
        Add node, with information filled in, to grpc manager
        """
        node_id = self.next_node_id()
        position = Position(x=x, y=y)
        image = None
        if nutils.has_image(node_type):
            image = "ubuntu:latest"
        emane = None
        if node_type == NodeType.EMANE:
            if not self.session.emane_models:
                dialog = EmaneInstallDialog(self.app)
                dialog.show()
                return
            emane = self.session.emane_models[0]
            name = f"emane{node_id}"
        elif node_type == NodeType.WIRELESS_LAN:
            name = f"wlan{node_id}"
        elif node_type in [NodeType.RJ45, NodeType.TUNNEL]:
            name = "unassigned"
        else:
            name = f"n{node_id}"
        node = Node(
            id=node_id,
            type=node_type,
            name=name,
            model=model,
            position=position,
            image=image,
            emane=emane,
        )
        if nutils.is_custom(node):
            services = nutils.get_custom_services(self.app.guiconfig, model)
            node.services = set(services)
        # assign default services to CORE node
        else:
            services = self.session.default_services.get(model)
            if services:
                node.services = services.copy()
        logging.info(
            "add node(%s) to session(%s), coordinates(%s, %s)",
            node.name,
            self.session.id,
            x,
            y,
        )
        self.session.nodes[node.id] = node
        return node

    def deleted_canvas_nodes(self, canvas_nodes: List[CanvasNode]) -> None:
        """
        remove the nodes selected by the user and anything related to that node
        such as link, configurations, interfaces
        """
        for canvas_node in canvas_nodes:
            node = canvas_node.core_node
            del self.canvas_nodes[node.id]
            del self.session.nodes[node.id]

    def deleted_canvas_edges(self, edges: Iterable[CanvasEdge]) -> None:
        links = []
        for edge in edges:
            del self.links[edge.token]
            links.append(edge.link)
        self.ifaces_manager.removed(links)

    def save_edge(self, edge: CanvasEdge) -> None:
        self.links[edge.token] = edge
        src_node = edge.src.core_node
        dst_node = edge.dst.core_node
        if nutils.is_container(src_node):
            src_iface_id = edge.link.iface1.id
            self.iface_to_edge[(src_node.id, src_iface_id)] = edge
        if nutils.is_container(dst_node):
            dst_iface_id = edge.link.iface2.id
            self.iface_to_edge[(dst_node.id, dst_iface_id)] = edge

    def get_wlan_configs_proto(self) -> List[wlan_pb2.WlanConfig]:
        configs = []
        for node in self.session.nodes.values():
            if node.type != NodeType.WIRELESS_LAN:
                continue
            if not node.wlan_config:
                continue
            config = ConfigOption.to_dict(node.wlan_config)
            wlan_config = wlan_pb2.WlanConfig(node_id=node.id, config=config)
            configs.append(wlan_config)
        return configs

    def get_mobility_configs_proto(self) -> List[mobility_pb2.MobilityConfig]:
        configs = []
        for node in self.session.nodes.values():
            if not nutils.is_mobility(node):
                continue
            if not node.mobility_config:
                continue
            config = ConfigOption.to_dict(node.mobility_config)
            mobility_config = mobility_pb2.MobilityConfig(
                node_id=node.id, config=config
            )
            configs.append(mobility_config)
        return configs

    def get_emane_model_configs_proto(self) -> List[emane_pb2.EmaneModelConfig]:
        configs = []
        for node in self.session.nodes.values():
            for key, config in node.emane_model_configs.items():
                model, iface_id = key
                config = ConfigOption.to_dict(config)
                if iface_id is None:
                    iface_id = -1
                config_proto = emane_pb2.EmaneModelConfig(
                    node_id=node.id, iface_id=iface_id, model=model, config=config
                )
                configs.append(config_proto)
        return configs

    def get_service_configs_proto(self) -> List[services_pb2.ServiceConfig]:
        configs = []
        for node in self.session.nodes.values():
            if not nutils.is_container(node):
                continue
            if not node.service_configs:
                continue
            for name, config in node.service_configs.items():
                config_proto = services_pb2.ServiceConfig(
                    node_id=node.id,
                    service=name,
                    directories=config.dirs,
                    files=config.configs,
                    startup=config.startup,
                    validate=config.validate,
                    shutdown=config.shutdown,
                )
                configs.append(config_proto)
        return configs

    def get_service_file_configs_proto(self) -> List[services_pb2.ServiceFileConfig]:
        configs = []
        for node in self.session.nodes.values():
            if not nutils.is_container(node):
                continue
            if not node.service_file_configs:
                continue
            for service, file_configs in node.service_file_configs.items():
                for file, data in file_configs.items():
                    config_proto = services_pb2.ServiceFileConfig(
                        node_id=node.id, service=service, file=file, data=data
                    )
                    configs.append(config_proto)
        return configs

    def get_config_service_configs_proto(
        self,
    ) -> List[configservices_pb2.ConfigServiceConfig]:
        config_service_protos = []
        for node in self.session.nodes.values():
            if not nutils.is_container(node):
                continue
            if not node.config_service_configs:
                continue
            for name, service_config in node.config_service_configs.items():
                config_proto = configservices_pb2.ConfigServiceConfig(
                    node_id=node.id,
                    name=name,
                    templates=service_config.templates,
                    config=service_config.config,
                )
                config_service_protos.append(config_proto)
        return config_service_protos

    def run(self, node_id: int) -> str:
        logging.info("running node(%s) cmd: %s", node_id, self.observer)
        return self.client.node_command(self.session.id, node_id, self.observer).output

    def get_wlan_config(self, node_id: int) -> Dict[str, ConfigOption]:
        response = self.client.get_wlan_config(self.session.id, node_id)
        config = response.config
        logging.debug(
            "get wlan configuration from node %s, result configuration: %s",
            node_id,
            config,
        )
        return ConfigOption.from_dict(config)

    def get_mobility_config(self, node_id: int) -> Dict[str, ConfigOption]:
        response = self.client.get_mobility_config(self.session.id, node_id)
        config = response.config
        logging.debug(
            "get mobility config from node %s, result configuration: %s",
            node_id,
            config,
        )
        return ConfigOption.from_dict(config)

    def get_emane_model_config(
        self, node_id: int, model: str, iface_id: int = None
    ) -> Dict[str, ConfigOption]:
        if iface_id is None:
            iface_id = -1
        response = self.client.get_emane_model_config(
            self.session.id, node_id, model, iface_id
        )
        config = response.config
        logging.debug(
            "get emane model config: node id: %s, EMANE model: %s, "
            "interface: %s, config: %s",
            node_id,
            model,
            iface_id,
            config,
        )
        return ConfigOption.from_dict(config)

    def execute_script(self, script) -> None:
        response = self.client.execute_script(script)
        logging.info("execute python script %s", response)
        if response.session_id != -1:
            self.join_session(response.session_id)

    def add_link(self, link: Link) -> None:
        iface1 = link.iface1.to_proto() if link.iface1 else None
        iface2 = link.iface2.to_proto() if link.iface2 else None
        options = link.options.to_proto() if link.options else None
        response = self.client.add_link(
            self.session.id,
            link.node1_id,
            link.node2_id,
            iface1,
            iface2,
            options,
            source=GUI_SOURCE,
        )
        logging.debug("added link: %s", response)
        if not response.result:
            logging.error("error adding link: %s", link)

    def edit_link(self, link: Link) -> None:
        iface1_id = link.iface1.id if link.iface1 else None
        iface2_id = link.iface2.id if link.iface2 else None
        response = self.client.edit_link(
            self.session.id,
            link.node1_id,
            link.node2_id,
            link.options.to_proto(),
            iface1_id,
            iface2_id,
            source=GUI_SOURCE,
        )
        if not response.result:
            logging.error("error editing link: %s", link)
