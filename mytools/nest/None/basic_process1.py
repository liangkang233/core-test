# required imports
# coding: utf-8

from core import emane
from core.api.grpc import client, core_pb2
from core.api.grpc.wlan_pb2 import WlanConfig
from core.api.grpc.emane_pb2 import EmaneModelConfig
from core.api.grpc.core_pb2 import Node, NodeType, Position, SessionState
from core.api.grpc.mobility_pb2 import MobilityAction, MobilityConfig
from core.api.grpc.services_pb2 import ServiceAction, ServiceConfig, ServiceFileConfig
from core.emane.rfpipe import EmaneRfPipeModel
from core.emane.ieee80211abg import EmaneIeee80211abgModel
from core.nodes.network import SwitchNode, WlanNode
from core.emulator.enumerations import NodeTypes



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


# change session state to configuration so that nodes get started when added
core.set_session_state(session_id, SessionState.CONFIGURATION)

#distribute
# server_name="core1"
# core.add_session_server(session_id,server_name,"192.168.163.134")

#set controlnet
# core.set_session_options(session_id,{"controlnet":"172.18.1.0/24"})


## creat node iface link
node_num = 4
nodes, ifaces, links = [], [], []
for i in range(node_num):
    position = Position(x=(80*i), y=(80*i))
    node = Node(
            id=i+1,
            position=position,
            model="mdr", 
            name=f"N{i+1}",
            services=set([] + default_services["mdr"] + ["UserDefined"]),
            server=""
            # server=server_name
            )
    iface = iface_helper.create_iface(node.id, 0)
    nodes.append(node)
    ifaces.append(iface)

wlan_node = Node(
            id=node_num+1,
            type=NodeTypes.EMANE.value,
            position=Position(x=500, y=300),
            emane=EmaneRfPipeModel.name,
            name=f"Nw{node_num+1}",
            )
nodes.append(wlan_node)
iface = iface_helper.create_iface(wlan_node.id, 0)
ifaces.append(iface)

for i in range(node_num):
    link = core_pb2.Link(node1_id=nodes[i].id, node2_id=nodes[node_num].id,
                         type=core_pb2.LinkType.WIRED, iface1=ifaces[i])
    links.append(link)


## location
location = core_pb2.SessionLocation(
    x = 0,
    y = 0,
    z = 0,
    lat = 29.5397,
    lon = 106.6032,
    alt = 10,
    scale = 150.0,
)


## hook
hook = core_pb2.Hook(
    state=core_pb2.SessionState.RUNTIME, file="echo.sh", data="touch /home/lk233/桌面/1"
)
hooks = [hook]

## emane_config
emane_config = {"platform_id_start": "1"}

## model_configs
model_config = EmaneModelConfig(
    node_id=wlan_node.id,
    iface_id=-1,
    # model=EmaneIeee80211abgModel.name,
    model=EmaneRfPipeModel.name,
    config={"bandwidth": "500000"},
)
model_configs = [model_config]

## wlan_configs => basic model setting
# wlan_config_key = "range"
# wlan_config_value = "333"
# wlan_config = WlanConfig(
#     node_id=wlan_node.id, config={wlan_config_key: wlan_config_value}
# )
# wlan_configs = [wlan_config]

## mobility_configs
mobility_config = MobilityConfig(
    node_id=wlan_node.id, config={
        "refresh_ms": "60",
        "file": "sample1.scen",
        "autostart": "5.0",
        "loop": "1",
        "script_start": "",
        "script_pause": "",
        "script_stop": "",
        }
)
mobility_configs = [mobility_config]


## service_configs and service_file_configs
service_configs = [[]for i in range(node_num)]
service_file_configs = [[]for i in range(node_num)]

for j in range(node_num) :
    if j % 2:
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


core.start_session(
    session_id,
    nodes,
    links,
    location = location,
    # hooks = hooks,
    emane_config = emane_config,
    emane_model_configs = model_configs,
    # wlan_configs = wlan_configs,
    mobility_configs = mobility_configs,
    service_configs = service_configs,
    service_file_configs = service_file_configs,
    # config_service_configs = config_service_configs,
)

print(core.get_emane_event_channel(session_id))

core.save_xml(session_id, "/home/lk233/core/mytools/nest/xmls/test1.xml")

input("stop")
core.stop_session(session_id)
core.delete_session(session_id)

