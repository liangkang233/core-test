"""
gRpc client for interfacing with CORE.
"""

import logging
import threading
from contextlib import contextmanager
from queue import Queue
from typing import Any, Callable, Dict, Generator, Iterable, List, Optional, Tuple

import grpc

from core.api.grpc import (
    configservices_pb2,
    core_pb2,
    core_pb2_grpc,
    emane_pb2,
    mobility_pb2,
    services_pb2,
    wlan_pb2,
    wrappers,
)
from core.api.grpc.configservices_pb2 import (
    GetConfigServiceDefaultsRequest,
    GetConfigServicesRequest,
    GetNodeConfigServiceConfigsRequest,
    GetNodeConfigServiceRequest,
    GetNodeConfigServicesRequest,
    SetNodeConfigServiceRequest,
)
from core.api.grpc.core_pb2 import ExecuteScriptRequest
from core.api.grpc.emane_pb2 import (
    EmaneLinkRequest,
    GetEmaneConfigRequest,
    GetEmaneEventChannelRequest,
    GetEmaneModelConfigRequest,
    GetEmaneModelConfigsRequest,
    GetEmaneModelsRequest,
    SetEmaneConfigRequest,
    SetEmaneModelConfigRequest,
)
from core.api.grpc.mobility_pb2 import (
    GetMobilityConfigRequest,
    GetMobilityConfigsRequest,
    MobilityActionRequest,
    MobilityConfig,
    SetMobilityConfigRequest,
)
from core.api.grpc.services_pb2 import (
    GetNodeServiceConfigsRequest,
    GetNodeServiceFileRequest,
    GetNodeServiceRequest,
    GetServiceDefaultsRequest,
    GetServicesRequest,
    ServiceActionRequest,
    ServiceDefaults,
    ServiceFileConfig,
    SetNodeServiceFileRequest,
    SetNodeServiceRequest,
    SetServiceDefaultsRequest,
)
from core.api.grpc.wlan_pb2 import (
    GetWlanConfigRequest,
    GetWlanConfigsRequest,
    SetWlanConfigRequest,
    WlanConfig,
    WlanLinkRequest,
)
from core.emulator.data import IpPrefixes


class MoveNodesStreamer:
    def __init__(self, session_id: int = None, source: str = None) -> None:
        self.session_id = session_id
        self.source = source
        self.queue: Queue = Queue()

    def send_position(self, node_id: int, x: float, y: float) -> None:
        position = wrappers.Position(x=x, y=y)
        request = wrappers.MoveNodesRequest(
            session_id=self.session_id,
            node_id=node_id,
            source=self.source,
            position=position,
        )
        self.send(request)

    def send_geo(self, node_id: int, lon: float, lat: float, alt: float) -> None:
        geo = wrappers.Geo(lon=lon, lat=lat, alt=alt)
        request = wrappers.MoveNodesRequest(
            session_id=self.session_id, node_id=node_id, source=self.source, geo=geo
        )
        self.send(request)

    def send(self, request: wrappers.MoveNodesRequest) -> None:
        self.queue.put(request)

    def stop(self) -> None:
        self.queue.put(None)

    def next(self) -> Optional[core_pb2.MoveNodesRequest]:
        request: Optional[wrappers.MoveNodesRequest] = self.queue.get()
        if request:
            return request.to_proto()
        else:
            return request

    def iter(self) -> Iterable:
        return iter(self.next, None)


class EmanePathlossesStreamer:
    def __init__(self) -> None:
        self.queue: Queue = Queue()

    def send(self, request: Optional[wrappers.EmanePathlossesRequest]) -> None:
        self.queue.put(request)

    def next(self) -> Optional[emane_pb2.EmanePathlossesRequest]:
        request: Optional[wrappers.EmanePathlossesRequest] = self.queue.get()
        if request:
            return request.to_proto()
        else:
            return request

    def iter(self):
        return iter(self.next, None)


class InterfaceHelper:
    """
    Convenience class to help generate IP4 and IP6 addresses for gRPC clients.
    """

    def __init__(self, ip4_prefix: str = None, ip6_prefix: str = None) -> None:
        """
        Creates an InterfaceHelper object.

        :param ip4_prefix: ip4 prefix to use for generation
        :param ip6_prefix: ip6 prefix to use for generation
        :raises ValueError: when both ip4 and ip6 prefixes have not been provided
        """
        self.prefixes: IpPrefixes = IpPrefixes(ip4_prefix, ip6_prefix)

    def create_iface(
        self, node_id: int, iface_id: int, name: str = None, mac: str = None
    ) -> wrappers.Interface:
        """
        Create an interface protobuf object.

        :param node_id: node id to create interface for
        :param iface_id: interface id
        :param name: name of interface
        :param mac: mac address for interface
        :return: interface protobuf
        """
        iface_data = self.prefixes.gen_iface(node_id, name, mac)
        return wrappers.Interface(
            id=iface_id,
            name=iface_data.name,
            ip4=iface_data.ip4,
            ip4_mask=iface_data.ip4_mask,
            ip6=iface_data.ip6,
            ip6_mask=iface_data.ip6_mask,
            mac=iface_data.mac,
        )


def throughput_listener(
    stream: Any, handler: Callable[[wrappers.ThroughputsEvent], None]
) -> None:
    """
    Listen for throughput events and provide them to the handler.

    :param stream: grpc stream that will provide events
    :param handler: function that handles an event
    :return: nothing
    """
    try:
        for event_proto in stream:
            event = wrappers.ThroughputsEvent.from_proto(event_proto)
            handler(event)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.CANCELLED:
            logging.debug("throughput stream closed")
        else:
            logging.exception("throughput stream error")


def cpu_listener(
    stream: Any, handler: Callable[[wrappers.CpuUsageEvent], None]
) -> None:
    """
    Listen for cpu events and provide them to the handler.

    :param stream: grpc stream that will provide events
    :param handler: function that handles an event
    :return: nothing
    """
    try:
        for event_proto in stream:
            event = wrappers.CpuUsageEvent.from_proto(event_proto)
            handler(event)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.CANCELLED:
            logging.debug("cpu stream closed")
        else:
            logging.exception("cpu stream error")


def event_listener(stream: Any, handler: Callable[[wrappers.Event], None]) -> None:
    """
    Listen for session events and provide them to the handler.

    :param stream: grpc stream that will provide events
    :param handler: function that handles an event
    :return: nothing
    """
    try:
        for event_proto in stream:
            event = wrappers.Event.from_proto(event_proto)
            handler(event)
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.CANCELLED:
            logging.debug("session stream closed")
        else:
            logging.exception("session stream error")


class CoreGrpcClient:
    """
    Provides convenience methods for interfacing with the CORE grpc server.
    """

    def __init__(self, address: str = "localhost:50051", proxy: bool = False) -> None:
        """
        Creates a CoreGrpcClient instance.

        :param address: grpc server address to connect to
        """
        self.address: str = address
        self.stub: Optional[core_pb2_grpc.CoreApiStub] = None
        self.channel: Optional[grpc.Channel] = None
        self.proxy: bool = proxy

    def start_session(
        self, session: wrappers.Session, asymmetric_links: List[wrappers.Link] = None
    ) -> Tuple[bool, List[str]]:
        """
        Start a session.

        :param session: session to start
        :param asymmetric_links: link configuration for asymmetric links
        :return: tuple of result and exception strings
        """
        nodes = [x.to_proto() for x in session.nodes.values()]
        links = [x.to_proto() for x in session.links]
        if asymmetric_links:
            asymmetric_links = [x.to_proto() for x in asymmetric_links]
        hooks = [x.to_proto() for x in session.hooks.values()]
        emane_config = {k: v.value for k, v in session.emane_config.items()}
        emane_model_configs = []
        mobility_configs = []
        wlan_configs = []
        service_configs = []
        service_file_configs = []
        config_service_configs = []
        for node in session.nodes.values():
            for key, config in node.emane_model_configs.items():
                model, iface_id = key
                config = wrappers.ConfigOption.to_dict(config)
                if iface_id is None:
                    iface_id = -1
                emane_model_config = emane_pb2.EmaneModelConfig(
                    node_id=node.id, iface_id=iface_id, model=model, config=config
                )
                emane_model_configs.append(emane_model_config)
            if node.wlan_config:
                config = wrappers.ConfigOption.to_dict(node.wlan_config)
                wlan_config = wlan_pb2.WlanConfig(node_id=node.id, config=config)
                wlan_configs.append(wlan_config)
            if node.mobility_config:
                config = wrappers.ConfigOption.to_dict(node.mobility_config)
                mobility_config = mobility_pb2.MobilityConfig(
                    node_id=node.id, config=config
                )
                mobility_configs.append(mobility_config)
            for name, config in node.service_configs.items():
                service_config = services_pb2.ServiceConfig(
                    node_id=node.id,
                    service=name,
                    directories=config.dirs,
                    files=config.configs,
                    startup=config.startup,
                    validate=config.validate,
                    shutdown=config.shutdown,
                )
                service_configs.append(service_config)
            for service, file_configs in node.service_file_configs.items():
                for file, data in file_configs.items():
                    service_file_config = services_pb2.ServiceFileConfig(
                        node_id=node.id, service=service, file=file, data=data
                    )
                    service_file_configs.append(service_file_config)
            for name, service_config in node.config_service_configs.items():
                config_service_config = configservices_pb2.ConfigServiceConfig(
                    node_id=node.id,
                    name=name,
                    templates=service_config.templates,
                    config=service_config.config,
                )
                config_service_configs.append(config_service_config)
        request = core_pb2.StartSessionRequest(
            session_id=session.id,
            nodes=nodes,
            links=links,
            location=session.location.to_proto(),
            hooks=hooks,
            emane_config=emane_config,
            emane_model_configs=emane_model_configs,
            wlan_configs=wlan_configs,
            mobility_configs=mobility_configs,
            service_configs=service_configs,
            service_file_configs=service_file_configs,
            asymmetric_links=asymmetric_links,
            config_service_configs=config_service_configs,
        )
        response = self.stub.StartSession(request)
        return response.result, list(response.exceptions)

    def stop_session(self, session_id: int) -> bool:
        """
        Stop a running session.

        :param session_id: id of session
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.StopSessionRequest(session_id=session_id)
        response = self.stub.StopSession(request)
        return response.result

    def create_session(self, session_id: int = None) -> int:
        """
        Create a session.

        :param session_id: id for session, default is None and one will be created
            for you
        :return: session id
        """
        request = core_pb2.CreateSessionRequest(session_id=session_id)
        response = self.stub.CreateSession(request)
        return response.session_id

    def delete_session(self, session_id: int) -> bool:
        """
        Delete a session.

        :param session_id: id of session
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.DeleteSessionRequest(session_id=session_id)
        response = self.stub.DeleteSession(request)
        return response.result

    def get_sessions(self) -> List[wrappers.SessionSummary]:
        """
        Retrieves all currently known sessions.

        :return: response with a list of currently known session, their state and
            number of nodes
        """
        response = self.stub.GetSessions(core_pb2.GetSessionsRequest())
        sessions = []
        for session_proto in response.sessions:
            session = wrappers.SessionSummary.from_proto(session_proto)
            sessions.append(session)
        return sessions

    def check_session(self, session_id: int) -> bool:
        """
        Check if a session exists.

        :param session_id: id of session to check for
        :return: True if exists, False otherwise
        """
        request = core_pb2.CheckSessionRequest(session_id=session_id)
        response = self.stub.CheckSession(request)
        return response.result

    def get_session(self, session_id: int) -> wrappers.Session:
        """
        Retrieve a session.

        :param session_id: id of session
        :return: session
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.GetSessionRequest(session_id=session_id)
        response = self.stub.GetSession(request)
        return wrappers.Session.from_proto(response.session)

    def get_session_options(self, session_id: int) -> Dict[str, wrappers.ConfigOption]:
        """
        Retrieve session options as a dict with id mapping.

        :param session_id: id of session
        :return: session configuration options
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.GetSessionOptionsRequest(session_id=session_id)
        response = self.stub.GetSessionOptions(request)
        return wrappers.ConfigOption.from_dict(response.config)

    def set_session_options(self, session_id: int, config: Dict[str, str]) -> bool:
        """
        Set options for a session.

        :param session_id: id of session
        :param config: configuration values to set
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.SetSessionOptionsRequest(
            session_id=session_id, config=config
        )
        response = self.stub.SetSessionOptions(request)
        return response.result

    def get_session_metadata(self, session_id: int) -> Dict[str, str]:
        """
        Retrieve session metadata as a dict with id mapping.

        :param session_id: id of session
        :return: response with metadata dict
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.GetSessionMetadataRequest(session_id=session_id)
        response = self.stub.GetSessionMetadata(request)
        return dict(response.config)

    def set_session_metadata(self, session_id: int, config: Dict[str, str]) -> bool:
        """
        Set metadata for a session.

        :param session_id: id of session
        :param config: configuration values to set
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.SetSessionMetadataRequest(
            session_id=session_id, config=config
        )
        response = self.stub.SetSessionMetadata(request)
        return response.result

    def get_session_location(self, session_id: int) -> wrappers.SessionLocation:
        """
        Get session location.

        :param session_id: id of session
        :return: response with session position reference and scale
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.GetSessionLocationRequest(session_id=session_id)
        response = self.stub.GetSessionLocation(request)
        return wrappers.SessionLocation.from_proto(response.location)

    def set_session_location(
        self, session_id: int, location: wrappers.SessionLocation
    ) -> bool:
        """
        Set session location.

        :param session_id: id of session
        :param location: session location
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.SetSessionLocationRequest(
            session_id=session_id, location=location.to_proto()
        )
        response = self.stub.SetSessionLocation(request)
        return response.result

    def set_session_state(self, session_id: int, state: wrappers.SessionState) -> bool:
        """
        Set session state.

        :param session_id: id of session
        :param state: session state to transition to
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.SetSessionStateRequest(
            session_id=session_id, state=state.value
        )
        response = self.stub.SetSessionState(request)
        return response.result

    def set_session_user(self, session_id: int, user: str) -> bool:
        """
        Set session user, used for helping to find files without full paths.

        :param session_id: id of session
        :param user: user to set for session
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.SetSessionUserRequest(session_id=session_id, user=user)
        response = self.stub.SetSessionUser(request)
        return response.result

    def add_session_server(self, session_id: int, name: str, host: str) -> bool:
        """
        Add distributed session server.

        :param session_id: id of session
        :param name: name of server to add
        :param host: host address to connect to
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.AddSessionServerRequest(
            session_id=session_id, name=name, host=host
        )
        response = self.stub.AddSessionServer(request)
        return response.result

    def alert(
        self,
        session_id: int,
        level: wrappers.ExceptionLevel,
        source: str,
        text: str,
        node_id: int = None,
    ) -> bool:
        """
        Initiate an alert to be broadcast out to all listeners.

        :param session_id: id of session
        :param level: alert level
        :param source: source of alert
        :param text: alert text
        :param node_id: node associated with alert
        :return: True for success, False otherwise
        """
        request = core_pb2.SessionAlertRequest(
            session_id=session_id,
            level=level.value,
            source=source,
            text=text,
            node_id=node_id,
        )
        response = self.stub.SessionAlert(request)
        return response.result

    def events(
        self,
        session_id: int,
        handler: Callable[[wrappers.Event], None],
        events: List[wrappers.EventType] = None,
    ) -> grpc.Future:
        """
        Listen for session events.

        :param session_id: id of session
        :param handler: handler for received events
        :param events: events to listen to, defaults to all
        :return: stream processing events, can be used to cancel stream
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.EventsRequest(session_id=session_id, events=events)
        stream = self.stub.Events(request)
        thread = threading.Thread(
            target=event_listener, args=(stream, handler), daemon=True
        )
        thread.start()
        return stream

    def throughputs(
        self, session_id: int, handler: Callable[[wrappers.ThroughputsEvent], None]
    ) -> grpc.Future:
        """
        Listen for throughput events with information for interfaces and bridges.

        :param session_id: session id
        :param handler: handler for every event
        :return: stream processing events, can be used to cancel stream
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.ThroughputsRequest(session_id=session_id)
        stream = self.stub.Throughputs(request)
        thread = threading.Thread(
            target=throughput_listener, args=(stream, handler), daemon=True
        )
        thread.start()
        return stream

    def cpu_usage(
        self, delay: int, handler: Callable[[wrappers.CpuUsageEvent], None]
    ) -> grpc.Future:
        """
        Listen for cpu usage events with the given repeat delay.

        :param delay: delay between receiving events
        :param handler: handler for every event
        :return: stream processing events, can be used to cancel stream
        """
        request = core_pb2.CpuUsageRequest(delay=delay)
        stream = self.stub.CpuUsage(request)
        thread = threading.Thread(
            target=cpu_listener, args=(stream, handler), daemon=True
        )
        thread.start()
        return stream

    def add_node(self, session_id: int, node: wrappers.Node, source: str = None) -> int:
        """
        Add node to session.

        :param session_id: session id
        :param node: node to add
        :param source: source application
        :return: id of added node
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.AddNodeRequest(
            session_id=session_id, node=node.to_proto(), source=source
        )
        response = self.stub.AddNode(request)
        return response.node_id

    def get_node(
        self, session_id: int, node_id: int
    ) -> Tuple[wrappers.Node, List[wrappers.Interface]]:
        """
        Get node details.

        :param session_id: session id
        :param node_id: node id
        :return: tuple of node and its interfaces
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = core_pb2.GetNodeRequest(session_id=session_id, node_id=node_id)
        response = self.stub.GetNode(request)
        node = wrappers.Node.from_proto(response.node)
        ifaces = []
        for iface_proto in response.ifaces:
            iface = wrappers.Interface.from_proto(iface_proto)
            ifaces.append(iface)
        return node, ifaces

    def edit_node(
        self,
        session_id: int,
        node_id: int,
        position: wrappers.Position = None,
        icon: str = None,
        geo: wrappers.Geo = None,
        source: str = None,
    ) -> bool:
        """
        Edit a node's icon and/or location, can only use position(x,y) or
        geo(lon, lat, alt), not both.

        :param session_id: session id
        :param node_id: node id
        :param position: x,y location for node
        :param icon: path to icon for gui to use for node
        :param geo: lon,lat,alt location for node
        :param source: application source
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = core_pb2.EditNodeRequest(
            session_id=session_id,
            node_id=node_id,
            position=position.to_proto(),
            icon=icon,
            source=source,
            geo=geo.to_proto(),
        )
        response = self.stub.EditNode(request)
        return response.result

    def move_nodes(self, streamer: MoveNodesStreamer) -> None:
        """
        Stream node movements using the provided iterator.

        :param streamer: move nodes streamer
        :return: nothing
        :raises grpc.RpcError: when session or nodes do not exist
        """
        self.stub.MoveNodes(streamer.iter())

    def delete_node(self, session_id: int, node_id: int, source: str = None) -> bool:
        """
        Delete node from session.

        :param session_id: session id
        :param node_id: node id
        :param source: application source
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.DeleteNodeRequest(
            session_id=session_id, node_id=node_id, source=source
        )
        response = self.stub.DeleteNode(request)
        return response.result

    def node_command(
        self,
        session_id: int,
        node_id: int,
        command: str,
        wait: bool = True,
        shell: bool = False,
    ) -> Tuple[int, str]:
        """
        Send command to a node and get the output.

        :param session_id: session id
        :param node_id: node id
        :param command: command to run on node
        :param wait: wait for command to complete
        :param shell: send shell command
        :return: returns tuple of return code and output
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = core_pb2.NodeCommandRequest(
            session_id=session_id,
            node_id=node_id,
            command=command,
            wait=wait,
            shell=shell,
        )
        response = self.stub.NodeCommand(request)
        return response.return_code, response.output

    def get_node_terminal(self, session_id: int, node_id: int) -> str:
        """
        Retrieve terminal command string for launching a local terminal.

        :param session_id: session id
        :param node_id: node id
        :return: node terminal
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = core_pb2.GetNodeTerminalRequest(
            session_id=session_id, node_id=node_id
        )
        response = self.stub.GetNodeTerminal(request)
        return response.terminal

    def get_node_links(self, session_id: int, node_id: int) -> List[wrappers.Link]:
        """
        Get current links for a node.

        :param session_id: session id
        :param node_id: node id
        :return: list of links
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = core_pb2.GetNodeLinksRequest(session_id=session_id, node_id=node_id)
        response = self.stub.GetNodeLinks(request)
        links = []
        for link_proto in response.links:
            link = wrappers.Link.from_proto(link_proto)
            links.append(link)
        return links

    def add_link(
        self, session_id: int, link: wrappers.Link, source: str = None
    ) -> Tuple[bool, wrappers.Interface, wrappers.Interface]:
        """
        Add a link between nodes.

        :param session_id: session id
        :param link: link to add
        :param source: application source
        :return: tuple of result and finalized interface values
        :raises grpc.RpcError: when session or one of the nodes don't exist
        """
        request = core_pb2.AddLinkRequest(
            session_id=session_id, link=link.to_proto(), source=source
        )
        response = self.stub.AddLink(request)
        iface1 = wrappers.Interface.from_proto(response.iface1)
        iface2 = wrappers.Interface.from_proto(response.iface2)
        return response.result, iface1, iface2

    def edit_link(
        self, session_id: int, link: wrappers.Link, source: str = None
    ) -> bool:
        """
        Edit a link between nodes.

        :param session_id: session id
        :param link: link to edit
        :param source: application source
        :return: response with result of success or failure
        :raises grpc.RpcError: when session or one of the nodes don't exist
        """
        iface1_id = link.iface1.id if link.iface1 else None
        iface2_id = link.iface2.id if link.iface2 else None
        request = core_pb2.EditLinkRequest(
            session_id=session_id,
            node1_id=link.node1_id,
            node2_id=link.node2_id,
            options=link.options.to_proto(),
            iface1_id=iface1_id,
            iface2_id=iface2_id,
            source=source,
        )
        response = self.stub.EditLink(request)
        return response.result

    def delete_link(
        self, session_id: int, link: wrappers.Link, source: str = None
    ) -> bool:
        """
        Delete a link between nodes.

        :param session_id: session id
        :param link: link to delete
        :param source: application source
        :return: response with result of success or failure
        :raises grpc.RpcError: when session doesn't exist
        """
        iface1_id = link.iface1.id if link.iface1 else None
        iface2_id = link.iface2.id if link.iface2 else None
        request = core_pb2.DeleteLinkRequest(
            session_id=session_id,
            node1_id=link.node1_id,
            node2_id=link.node2_id,
            iface1_id=iface1_id,
            iface2_id=iface2_id,
            source=source,
        )
        response = self.stub.DeleteLink(request)
        return response.result

    def get_hooks(self, session_id: int) -> List[wrappers.Hook]:
        """
        Get all hook scripts.

        :param session_id: session id
        :return: list of hooks
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.GetHooksRequest(session_id=session_id)
        response = self.stub.GetHooks(request)
        hooks = []
        for hook_proto in response.hooks:
            hook = wrappers.Hook.from_proto(hook_proto)
            hooks.append(hook)
        return hooks

    def add_hook(
        self,
        session_id: int,
        state: wrappers.SessionState,
        file_name: str,
        file_data: str,
    ) -> bool:
        """
        Add hook scripts.

        :param session_id: session id
        :param state: state to trigger hook
        :param file_name: name of file for hook script
        :param file_data: hook script contents
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        hook = core_pb2.Hook(state=state.value, file=file_name, data=file_data)
        request = core_pb2.AddHookRequest(session_id=session_id, hook=hook)
        response = self.stub.AddHook(request)
        return response.result

    def get_mobility_configs(
        self, session_id: int
    ) -> Dict[int, Dict[str, wrappers.ConfigOption]]:
        """
        Get all mobility configurations.

        :param session_id: session id
        :return: dict of node id to mobility configuration dict
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetMobilityConfigsRequest(session_id=session_id)
        response = self.stub.GetMobilityConfigs(request)
        configs = {}
        for node_id, mapped_config in response.configs.items():
            configs[node_id] = wrappers.ConfigOption.from_dict(mapped_config.config)
        return configs

    def get_mobility_config(
        self, session_id: int, node_id: int
    ) -> Dict[str, wrappers.ConfigOption]:
        """
        Get mobility configuration for a node.

        :param session_id: session id
        :param node_id: node id
        :return: dict of config name to options
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = GetMobilityConfigRequest(session_id=session_id, node_id=node_id)
        response = self.stub.GetMobilityConfig(request)
        return wrappers.ConfigOption.from_dict(response.config)

    def set_mobility_config(
        self, session_id: int, node_id: int, config: Dict[str, str]
    ) -> bool:
        """
        Set mobility configuration for a node.

        :param session_id: session id
        :param node_id: node id
        :param config: mobility configuration
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or node doesn't exist
        """
        mobility_config = MobilityConfig(node_id=node_id, config=config)
        request = SetMobilityConfigRequest(
            session_id=session_id, mobility_config=mobility_config
        )
        response = self.stub.SetMobilityConfig(request)
        return response.result

    def mobility_action(
        self, session_id: int, node_id: int, action: wrappers.MobilityAction
    ) -> bool:
        """
        Send a mobility action for a node.

        :param session_id: session id
        :param node_id: node id
        :param action: action to take
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = MobilityActionRequest(
            session_id=session_id, node_id=node_id, action=action.value
        )
        response = self.stub.MobilityAction(request)
        return response.result

    def get_services(self) -> List[wrappers.Service]:
        """
        Get all currently loaded services.

        :return: list of services, name and groups only
        """
        request = GetServicesRequest()
        response = self.stub.GetServices(request)
        services = []
        for service_proto in response.services:
            service = wrappers.Service.from_proto(service_proto)
            services.append(service)
        return services

    def get_service_defaults(self, session_id: int) -> List[wrappers.ServiceDefault]:
        """
        Get default services for different default node models.

        :param session_id: session id
        :return: list of service defaults
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetServiceDefaultsRequest(session_id=session_id)
        response = self.stub.GetServiceDefaults(request)
        defaults = []
        for default_proto in response.defaults:
            default = wrappers.ServiceDefault.from_proto(default_proto)
            defaults.append(default)
        return defaults

    def set_service_defaults(
        self, session_id: int, service_defaults: Dict[str, List[str]]
    ) -> bool:
        """
        Set default services for node models.

        :param session_id: session id
        :param service_defaults: node models to lists of services
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        defaults = []
        for node_type in service_defaults:
            services = service_defaults[node_type]
            default = ServiceDefaults(node_type=node_type, services=services)
            defaults.append(default)
        request = SetServiceDefaultsRequest(session_id=session_id, defaults=defaults)
        response = self.stub.SetServiceDefaults(request)
        return response.result

    def get_node_service_configs(
        self, session_id: int
    ) -> List[wrappers.NodeServiceData]:
        """
        Get service data for a node.

        :param session_id: session id
        :return: list of node service data
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetNodeServiceConfigsRequest(session_id=session_id)
        response = self.stub.GetNodeServiceConfigs(request)
        node_services = []
        for service_proto in response.configs:
            node_service = wrappers.NodeServiceData.from_proto(service_proto)
            node_services.append(node_service)
        return node_services

    def get_node_service(
        self, session_id: int, node_id: int, service: str
    ) -> wrappers.NodeServiceData:
        """
        Get service data for a node.

        :param session_id: session id
        :param node_id: node id
        :param service: service name
        :return: node service data
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = GetNodeServiceRequest(
            session_id=session_id, node_id=node_id, service=service
        )
        response = self.stub.GetNodeService(request)
        return wrappers.NodeServiceData.from_proto(response.service)

    def get_node_service_file(
        self, session_id: int, node_id: int, service: str, file_name: str
    ) -> str:
        """
        Get a service file for a node.

        :param session_id: session id
        :param node_id: node id
        :param service: service name
        :param file_name: file name to get data for
        :return: file data
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = GetNodeServiceFileRequest(
            session_id=session_id, node_id=node_id, service=service, file=file_name
        )
        response = self.stub.GetNodeServiceFile(request)
        return response.data

    def set_node_service(
        self, session_id: int, service_config: wrappers.ServiceConfig
    ) -> bool:
        """
        Set service data for a node.

        :param session_id: session id
        :param service_config: service configuration for a node
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = SetNodeServiceRequest(
            session_id=session_id, config=service_config.to_proto()
        )
        response = self.stub.SetNodeService(request)
        return response.result

    def set_node_service_file(
        self, session_id: int, node_id: int, service: str, file_name: str, data: str
    ) -> bool:
        """
        Set a service file for a node.

        :param session_id: session id
        :param node_id: node id
        :param service: service name
        :param file_name: file name to save
        :param data: data to save for file
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or node doesn't exist
        """
        config = ServiceFileConfig(
            node_id=node_id, service=service, file=file_name, data=data
        )
        request = SetNodeServiceFileRequest(session_id=session_id, config=config)
        response = self.stub.SetNodeServiceFile(request)
        return response.result

    def service_action(
        self,
        session_id: int,
        node_id: int,
        service: str,
        action: wrappers.ServiceAction,
    ) -> bool:
        """
        Send an action to a service for a node.

        :param session_id: session id
        :param node_id: node id
        :param service: service name
        :param action: action for service (start, stop, restart,
            validate)
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = ServiceActionRequest(
            session_id=session_id, node_id=node_id, service=service, action=action.value
        )
        response = self.stub.ServiceAction(request)
        return response.result

    def get_wlan_configs(
        self, session_id: int
    ) -> Dict[int, Dict[str, wrappers.ConfigOption]]:
        """
        Get all wlan configurations.

        :param session_id: session id
        :return: dict of node ids to dict of names to options
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetWlanConfigsRequest(session_id=session_id)
        response = self.stub.GetWlanConfigs(request)
        configs = {}
        for node_id, mapped_config in response.configs.items():
            configs[node_id] = wrappers.ConfigOption.from_dict(mapped_config.config)
        return configs

    def get_wlan_config(
        self, session_id: int, node_id: int
    ) -> Dict[str, wrappers.ConfigOption]:
        """
        Get wlan configuration for a node.

        :param session_id: session id
        :param node_id: node id
        :return: dict of names to options
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetWlanConfigRequest(session_id=session_id, node_id=node_id)
        response = self.stub.GetWlanConfig(request)
        return wrappers.ConfigOption.from_dict(response.config)

    def set_wlan_config(
        self, session_id: int, node_id: int, config: Dict[str, str]
    ) -> bool:
        """
        Set wlan configuration for a node.

        :param session_id: session id
        :param node_id: node id
        :param config: wlan configuration
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        wlan_config = WlanConfig(node_id=node_id, config=config)
        request = SetWlanConfigRequest(session_id=session_id, wlan_config=wlan_config)
        response = self.stub.SetWlanConfig(request)
        return response.result

    def get_emane_config(self, session_id: int) -> Dict[str, wrappers.ConfigOption]:
        """
        Get session emane configuration.

        :param session_id: session id
        :return: response with a list of configuration groups
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetEmaneConfigRequest(session_id=session_id)
        response = self.stub.GetEmaneConfig(request)
        return wrappers.ConfigOption.from_dict(response.config)

    def set_emane_config(self, session_id: int, config: Dict[str, str]) -> bool:
        """
        Set session emane configuration.

        :param session_id: session id
        :param config: emane configuration
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = SetEmaneConfigRequest(session_id=session_id, config=config)
        response = self.stub.SetEmaneConfig(request)
        return response.result

    def get_emane_models(self, session_id: int) -> List[str]:
        """
        Get session emane models.

        :param session_id: session id
        :return: list of emane models
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetEmaneModelsRequest(session_id=session_id)
        response = self.stub.GetEmaneModels(request)
        return list(response.models)

    def get_emane_model_config(
        self, session_id: int, node_id: int, model: str, iface_id: int = -1
    ) -> Dict[str, wrappers.ConfigOption]:
        """
        Get emane model configuration for a node or a node's interface.

        :param session_id: session id
        :param node_id: node id
        :param model: emane model name
        :param iface_id: node interface id
        :return: dict of names to options
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetEmaneModelConfigRequest(
            session_id=session_id, node_id=node_id, model=model, iface_id=iface_id
        )
        response = self.stub.GetEmaneModelConfig(request)
        return wrappers.ConfigOption.from_dict(response.config)

    def set_emane_model_config(
        self, session_id: int, emane_model_config: wrappers.EmaneModelConfig
    ) -> bool:
        """
        Set emane model configuration for a node or a node's interface.

        :param session_id: session id
        :param emane_model_config: emane model config to set
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session doesn't exist
        """
        request = SetEmaneModelConfigRequest(
            session_id=session_id, emane_model_config=emane_model_config.to_proto()
        )
        response = self.stub.SetEmaneModelConfig(request)
        return response.result

    def get_emane_model_configs(
        self, session_id: int
    ) -> List[wrappers.EmaneModelConfig]:
        """
        Get all EMANE model configurations for a session.

        :param session_id: session to get emane model configs
        :return: list of emane model configs
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetEmaneModelConfigsRequest(session_id=session_id)
        response = self.stub.GetEmaneModelConfigs(request)
        configs = []
        for config_proto in response.configs:
            config = wrappers.EmaneModelConfig.from_proto(config_proto)
            configs.append(config)
        return configs

    def save_xml(self, session_id: int, file_path: str) -> None:
        """
        Save the current scenario to an XML file.

        :param session_id: session to save xml file for
        :param file_path: local path to save scenario XML file to
        :return: nothing
        :raises grpc.RpcError: when session doesn't exist
        """
        request = core_pb2.SaveXmlRequest(session_id=session_id)
        response = self.stub.SaveXml(request)
        with open(file_path, "w") as xml_file:
            xml_file.write(response.data)

    def open_xml(self, file_path: str, start: bool = False) -> Tuple[bool, int]:
        """
        Load a local scenario XML file to open as a new session.

        :param file_path: path of scenario XML file
        :param start: tuple of result and session id when successful
        :return: response with opened session id
        """
        with open(file_path, "r") as xml_file:
            data = xml_file.read()
        request = core_pb2.OpenXmlRequest(data=data, start=start, file=file_path)
        response = self.stub.OpenXml(request)
        return response.result, response.session_id

    def emane_link(self, session_id: int, nem1: int, nem2: int, linked: bool) -> bool:
        """
        Helps broadcast wireless link/unlink between EMANE nodes.

        :param session_id: session to emane link
        :param nem1: first nem for emane link
        :param nem2: second nem for emane link
        :param linked: True to link, False to unlink
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or nodes related to nems do not exist
        """
        request = EmaneLinkRequest(
            session_id=session_id, nem1=nem1, nem2=nem2, linked=linked
        )
        response = self.stub.EmaneLink(request)
        return response.result

    def get_ifaces(self) -> List[str]:
        """
        Retrieves a list of interfaces available on the host machine that are not
        a part of a CORE session.

        :return: list of interfaces
        """
        request = core_pb2.GetInterfacesRequest()
        response = self.stub.GetInterfaces(request)
        return list(response.ifaces)

    def get_config_services(self) -> List[wrappers.ConfigService]:
        """
        Retrieve all known config services.

        :return: list of config services
        """
        request = GetConfigServicesRequest()
        response = self.stub.GetConfigServices(request)
        services = []
        for service_proto in response.services:
            service = wrappers.ConfigService.from_proto(service_proto)
            services.append(service)
        return services

    def get_config_service_defaults(self, name: str) -> wrappers.ConfigServiceDefaults:
        """
        Retrieves config service default values.

        :param name: name of service to get defaults for
        :return: config service defaults
        """
        request = GetConfigServiceDefaultsRequest(name=name)
        response = self.stub.GetConfigServiceDefaults(request)
        return wrappers.ConfigServiceDefaults.from_proto(response)

    def get_node_config_service_configs(
        self, session_id: int
    ) -> List[wrappers.ConfigServiceConfig]:
        """
        Retrieves all node config service configurations for a session.

        :param session_id: session to get config service configurations for
        :return: list of node config service configs
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetNodeConfigServiceConfigsRequest(session_id=session_id)
        response = self.stub.GetNodeConfigServiceConfigs(request)
        configs = []
        for config_proto in response.configs:
            config = wrappers.ConfigServiceConfig.from_proto(config_proto)
            configs.append(config)
        return configs

    def get_node_config_service(
        self, session_id: int, node_id: int, name: str
    ) -> Dict[str, str]:
        """
        Retrieves information for a specific config service on a node.

        :param session_id: session node belongs to
        :param node_id: id of node to get service information from
        :param name: name of service
        :return: config dict of names to values
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = GetNodeConfigServiceRequest(
            session_id=session_id, node_id=node_id, name=name
        )
        response = self.stub.GetNodeConfigService(request)
        return dict(response.config)

    def get_node_config_services(self, session_id: int, node_id: int) -> List[str]:
        """
        Retrieves the config services currently assigned to a node.

        :param session_id: session node belongs to
        :param node_id: id of node to get config services for
        :return: list of config services
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = GetNodeConfigServicesRequest(session_id=session_id, node_id=node_id)
        response = self.stub.GetNodeConfigServices(request)
        return list(response.services)

    def set_node_config_service(
        self, session_id: int, node_id: int, name: str, config: Dict[str, str]
    ) -> bool:
        """
        Assigns a config service to a node with the provided configuration.

        :param session_id: session node belongs to
        :param node_id: id of node to assign config service to
        :param name: name of service
        :param config: service configuration
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or node doesn't exist
        """
        request = SetNodeConfigServiceRequest(
            session_id=session_id, node_id=node_id, name=name, config=config
        )
        response = self.stub.SetNodeConfigService(request)
        return response.result

    def get_emane_event_channel(self, session_id: int) -> wrappers.EmaneEventChannel:
        """
        Retrieves the current emane event channel being used for a session.

        :param session_id: session to get emane event channel for
        :return: emane event channel
        :raises grpc.RpcError: when session doesn't exist
        """
        request = GetEmaneEventChannelRequest(session_id=session_id)
        response = self.stub.GetEmaneEventChannel(request)
        return wrappers.EmaneEventChannel.from_proto(response)

    def execute_script(self, script: str) -> Optional[int]:
        """
        Executes a python script given context of the current CoreEmu object.

        :param script: script to execute
        :return: create session id for script executed
        """
        request = ExecuteScriptRequest(script=script)
        response = self.stub.ExecuteScript(request)
        return response.session_id if response.session_id else None

    def wlan_link(
        self, session_id: int, wlan_id: int, node1_id: int, node2_id: int, linked: bool
    ) -> bool:
        """
        Links/unlinks nodes on the same WLAN.

        :param session_id: session id containing wlan and nodes
        :param wlan_id: wlan nodes must belong to
        :param node1_id: first node of pair to link/unlink
        :param node2_id: second node of pair to link/unlin
        :param linked: True to link, False to unlink
        :return: True for success, False otherwise
        :raises grpc.RpcError: when session or one of the nodes do not exist
        """
        request = WlanLinkRequest(
            session_id=session_id,
            wlan=wlan_id,
            node1_id=node1_id,
            node2_id=node2_id,
            linked=linked,
        )
        response = self.stub.WlanLink(request)
        return response.result

    def emane_pathlosses(self, streamer: EmanePathlossesStreamer) -> None:
        """
        Stream EMANE pathloss events.

        :param streamer: emane pathlosses streamer
        :return: nothing
        :raises grpc.RpcError: when a pathloss event session or one of the nodes do not
            exist
        """
        self.stub.EmanePathlosses(streamer.iter())

    def connect(self) -> None:
        """
        Open connection to server, must be closed manually.

        :return: nothing
        """
        self.channel = grpc.insecure_channel(
            self.address, options=[("grpc.enable_http_proxy", self.proxy)]
        )
        self.stub = core_pb2_grpc.CoreApiStub(self.channel)

    def close(self) -> None:
        """
        Close currently opened server channel connection.

        :return: nothing
        """
        if self.channel:
            self.channel.close()
            self.channel = None

    @contextmanager
    def context_connect(self) -> Generator:
        """
        Makes a context manager based connection to the server, will close after
        context ends.

        :return: nothing
        """
        try:
            self.connect()
            yield
        finally:
            self.close()
