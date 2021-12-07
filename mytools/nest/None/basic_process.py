# required imports
# coding: utf-8

from re import S
from core.api.grpc import client
from core.api.grpc.core_pb2 import Node, NodeType, Position, SessionState
from core.emane.ieee80211abg import EmaneIeee80211abgModel
from core.emane.rfpipe import EmaneRfPipeModel
from core.api.grpc import configservices_pb2, core_pb2, core_pb2_grpc
from core.api.grpc.emane_pb2 import EmaneModelConfig
from core.api.grpc.wlan_pb2 import WlanConfig
from core.api.grpc.mobility_pb2 import MobilityAction, MobilityConfig
from core.api.grpc.services_pb2 import ServiceAction, ServiceConfig, ServiceFileConfig
from core.emulator.enumerations import EventTypes, ExceptionLevels, NodeTypes
from core.emulator.data import EventData, IpPrefixes, NodeData, NodeOptions
from core.nodes.base import CoreNode, CoreNodeBase
from core.nodes.network import SwitchNode, WlanNode
from core.api.grpc.grpcutils import convert_link


from core.api.grpc import events
from core.emulator.data import EventData
import time
from core.emulator.enumerations import (
    EventTypes,
    ExceptionLevels,
    LinkTypes,
    MessageFlags,
)

from core.emane.emanemanager import EmaneManager




default_services = {
    "mdr": ["zebra", "OSPFv3MDR", "IPForward"],
    "PC": ["DefaultRoute"],
    "prouter": [],
    "router": ["zebra", "OSPFv2", "OSPFv3", "IPForward"],
    "host": ["DefaultRoute", "SSH"],
}

# interface helper
iface_helper = client.InterfaceHelper(
    ip4_prefix="10.0.0.0/24", ip6_prefix="2001::/64")

# create grpc client and connect
core = client.CoreGrpcClient()
core.connect()

# create session and get id
response = core.create_session()
session_id = response.session_id

#distribute
server_name="core1"
core.add_session_server(session_id,server_name,"192.168.163.134")


# change session state to configuration so that nodes get started when added
core.set_session_state(session_id, SessionState.CONFIGURATION)

#set controlnet
core.set_session_options(session_id,{"controlnet":"172.18.1.0/24"})


# #creat node iface
node_num = 8
i = 1
j = 0
nodes = [[]for i in range(node_num+2)]
ifaces = [{}for i in range(node_num+1)]
links = [[]for i in range(node_num+1)]

while i <= node_num:
    position = Position(x=(80*i), y=(80*i))
    node = Node(id=i, position=position,
                model="mdr", name=f"N{i}",
                services=set([] + default_services["mdr"] +
                             ["UserDefined"]),
                server=""
                # server=server_name
                )
                
    nodes[j] = node
    iface = iface_helper.create_iface(nodes[j].id, 0)
    ifaces[j] = iface
    j = j+1
    i = i+1


position = Position(x=500, y=300)
wlan_node = Node(id=(node_num+1), type=NodeTypes.EMANE.value,
                 position=position, emane=EmaneRfPipeModel.name, name=f"Nw{node_num+1}"
                 )
nodes[node_num] = wlan_node

nodes[9]=Node(id=10, position=Position(x=600, y=300),
            model="mdr", name=f"N10",
            services=set([] + default_services["mdr"] +["UserDefined"]),
            server=server_name
            )
ifaces[8]=iface_helper.create_iface(nodes[9].id, 0)           
# response = core.add_session_server(session_id, "core1",)

# #creat link
def add_wireless_link(
    node1_id: int,
    node2_id: int,
    type=core_pb2.LinkType.WIRED,
    iface1: core_pb2.Interface = None,
    # iface2: core_pb2.Interface = None,
    )-> core_pb2.Link:
    link = core_pb2.Link(node1_id=node1_id, node2_id=node2_id,
                         type=type, iface1=iface1)
    return link 


i = 1
j = 0
while i <= node_num:
    link = core_pb2.Link(node1_id=nodes[j].id, node2_id=nodes[node_num].id,
                         type=core_pb2.LinkType.WIRED, iface1=ifaces[j])
    links[j] = link
    j = j+1
    i = i+1
links[8]=core_pb2.Link(node1_id=nodes[9].id, node2_id=nodes[node_num].id,
                         type=core_pb2.LinkType.WIRED, iface1=ifaces[8])
# links[8]=add_wireless_link(nodes[9].id,nodes[node_num].id,core_pb2.LinkType.WIRED,ifaces[8])
# link_proto = convert_link(link)


location_x = 5
location_y = 10
location_z = 15
location_lat = 20
location_lon = 30
location_alt = 40
location_scale = 5
location = core_pb2.SessionLocation(
    x=location_x,
    y=location_y,
    z=location_z,
    lat=location_lat,
    lon=location_lon,
    alt=location_alt,
    scale=location_scale,
)


hook = core_pb2.Hook(
    state=core_pb2.SessionState.RUNTIME, file="echo.sh", data="touch /home/lk233/桌面/1"
)
hooks = [hook]


emane_config_key = "platform_id_start"
emane_config_value = "1"
emane_config = {emane_config_key: emane_config_value}
model_node_id = (node_num+1)


model_config_key = "bandwidth"
model_config_value = "500000"
model_config = EmaneModelConfig(
    node_id=model_node_id,
    iface_id=-1,
    # model=EmaneIeee80211abgModel.name,
    model=EmaneRfPipeModel.name,
    config={model_config_key: model_config_value},
)
model_configs = [model_config]


# basic   setting
# wlan_config_key = "range"
# wlan_config_value = "333"
# wlan_config = WlanConfig(
#     node_id=wlan_node.id, config={wlan_config_key: wlan_config_value}
# )
# wlan_configs = [wlan_config]
wlan_configs = []


# mobility
mobility_config_key = "refresh_ms"
mobility_config_value = "60"
mobility_config_key1 = "file"
mobility_config_value1 = "/home/lk233/core/mytools/nest/xmls/sample1.scen"
mobility_config_key2 = "autostart"
mobility_config_value2 = "10"
mobility_config = MobilityConfig(
    node_id=wlan_node.id, config={
        mobility_config_key: mobility_config_value,
        mobility_config_key1: mobility_config_value1,
        mobility_config_key2: mobility_config_value2
        }
)
mobility_configs = [mobility_config]
""" # START = 7
# STOP = 8
# PAUSE = 9
# RESTART = 10
event_data = EventData(
    node=nodes[node_num].id,
    event_type=EventTypes.START,
    name="mobility:ns2script",
    # data=fail_data + ";" + unknown_data,
    time=str(time.monotonic()),
)

events.handle_session_event(event_data) """

# service
service_config = ServiceConfig(
    node_id=nodes[0].id, service="DefaultRoute", validate=["echo hello"]
)
service_configs = [service_config]
service_file_config = ServiceFileConfig(
    node_id=nodes[0].id,
    service="DefaultRoute",
    file="defaultroute.sh",
    data="echo hello",
)
service_file_configs = [service_file_config]


""" i = 1
j = 0
service_configs = [[]for i in range(node_num)]
service_file_configs = [[]for i in range(node_num)]

while j < node_num:
    if i % 2:
        service_config = ServiceConfig(
            node_id=nodes[j].id,
            service="UserDefined",
            directories=[], files=["test.sh"],
            startup=["bash test.sh"], validate=["echo hello"],
            shutdown=[]
        )
        service_configs[j] = service_config

        service_file_config = ServiceFileConfig(
            node_id=nodes[j].id,
            service="UserDefined",
            file="test.sh",
            data="iperf3 -s ",
        )
        service_file_configs[j] = service_file_config
    else:
        service_config = ServiceConfig(
            node_id=nodes[j].id, service="UserDefined",
            directories=[], files=["test.sh"], startup=["bash test.sh"],
            validate=["echo hello"], shutdown=[]
        )
        service_configs[j] = service_config

        service_file_config = ServiceFileConfig(
            node_id=nodes[j].id,
            service="UserDefined",
            file="test.sh",
            data="iperf3 -s",
        )
        service_file_configs[j] = service_file_config
    j = j+1
    i = i+1 """

""" 
service_config = ServiceConfig(
    node_id=nodes[0].id, service="IPForward", 
    directories=["/home/hyh/core/test1/"], files=["test1.sh"], startup=["bash test1.sh"], 
    validate=["echo hello"], shutdown=[]
)
service_configs.append(service_config) 

service_file_config = ServiceFileConfig(
    node_id=nodes[0].id,
    service="IPForward",
    file="test1.sh",
    data="ip route add default via 10.0.0.1",
)
service_file_configs.append(service_file_config) """


core.start_session(
    session_id,
    nodes,
    links,
    location,
    hooks,
    emane_config,
    model_configs,
    wlan_configs,
    mobility_configs,
    service_configs,
    service_file_configs,
    # config_service_configs=config_service_configs,
)

print(core.get_emane_event_channel(session_id))

core.save_xml(session_id, "/home/lk233/core/mytools/nest/xmls/test1.xml")

# input("press enter to exit")
# core.mobility_action(session_id,nodes[node_num].id,MobilityAction.STOP)


# change session state
# core.set_session_state(session_id, SessionState.INSTANTIATION)
# core.set_session_state(session_id, SessionState.SHUTDOWN)
# core.set_session_state(session_id, SessionState.RUNTIME)
