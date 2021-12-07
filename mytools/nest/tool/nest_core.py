"""
包含了对 json 包的解析与处理
并且实现了对 core grpc api 的仿真器调用
指令统一使用json封装，下面是具体细节
"""

from core.api.grpc import client, core_pb2
from core.api.grpc.wlan_pb2 import WlanConfig
from core.api.grpc.emane_pb2 import EmaneModelConfig
from core.api.grpc.core_pb2 import Node, NodeType, Position, SessionState
from core.api.grpc.mobility_pb2 import MobilityAction, MobilityConfig
from core.api.grpc.services_pb2 import ServiceAction, ServiceConfig, ServiceFileConfig
from core.emane import emanemodel
from core.nodes.network import SwitchNode, WlanNode
from core.emulator.enumerations import LinkTypes, NodeTypes

from enum import Enum, unique

from sql import nest_data
from tool.mylog import config, logger, scenario_path
import json
import os
import grpc

nodemodel = (
    "mdr",
    "PC",
    "host",
    "router",
)

Emanemodel = (
    "emane_rfpipe",
    "emane_ieee80211abg",
    "emane_tdma",
)

default_services = {
    "prouter": [],
    "PC": ["DefaultRoute"],
    "host": ["DefaultRoute", "SSH"],
    "mdr": ["zebra", "OSPFv3MDR", "IPForward"],
    "router": ["zebra", "OSPFv2", "OSPFv3", "IPForward"],
}

# 创建grpc客户端并连接coredaemon
core = client.CoreGrpcClient()
core.connect()


@unique
class Instr(Enum):
    created_session = 1
    start_session = 2
    run_node_cmd = 3
    stop_session = 4
    open_session = 5
    get_sessions = 6

    @classmethod
    def get(cls, name: str) -> "Instr":
        try:
            return Instr(name)
        except ValueError:
            return None


def pack_config(session_id, sqlconfig):
    """
    打包各项系统参数
    """
    # 设定控制网
    sql_config = sqlconfig[0]
    if sql_config["Ctrlnet0"]:
        core.set_session_options(session_id,{"controlnet0" : sql_config["Ctrlnet0"]})
    if sql_config["Ctrlnet1"]:
        core.set_session_options(session_id,{"controlnet1" : sql_config["Ctrlnet1"]})
    # 设定画布坐标
    location = core_pb2.SessionLocation( # 默认值
        x=0,
        y=0,
        z=0,
        lat=29.5397,
        lon=106.6032,
        alt=10,
        scale=150.0,
    )
    if sql_config["location"]:
        temp=sql_config["location"].split(":")
        location = core_pb2.SessionLocation(
            x = float (temp[0]),
            y = float (temp[1]),
            z = float (temp[2]),
            lat = float (temp[3]),
            lon = float (temp[4]),
            alt = float (temp[5]),
            scale = float (temp[6]),
        )
    # 添加分布式
    if sql_config["server"]:
        servers = sql_config["server"].split(";")
        for server in servers:
            temp=server.split(":")
            core.add_session_server(session_id,temp[0],temp[1])
    # 添加hook
    hooks=[]
    if sql_config["hook"]:
        hook1=sql_config["hook"].split(";")
        for hook2 in hook1:
            temp=hook2.split(":")
            hook = core_pb2.Hook(
                state=int(temp[0]), file=temp[1], data=temp[2]
            )
            hooks.append(hook)
    # 总体系统参数的emane配置
    emane_config={}
    if sql_config["emane_config"]:
        temp=sql_config["emane_config"].split(";")
        for temp1 in temp:
            temp2=temp1.split(":")
            emane_config[temp2[0]] = temp2[1]
    return location, hooks, emane_config


def pack_nodes(sqlnodes):
    """
    打包场景节点参数
    """
    nodes = []
    for sql_node in sqlnodes:
        xyz = sql_node["position"].split()
        model = None
        if not sql_node['model'] is None:
            model = nodemodel[sql_node['model']]
        emane_mod = None
        if not sql_node['emane'] is None:
            emane_mod = Emanemodel[sql_node['emane']]
        services = set()
        if sql_node['servers_set']:
            services = set(sql_node['servers_set'].split())
        elif not model is None:
            services = set(default_services[model])
        NN = Node(
            id=sql_node["nodeid"],
            name=f"N{sql_node['nodeid']}",
            position=Position(x=int(xyz[0]), y=int(xyz[1])),
            type=sql_node['types'],
            model=model,
            emane=emane_mod,
            services=services,
            server=sql_node["distribute"],
        )
        nodes.append(NN)
    return nodes


def pack_links(sqllinks):
    """
    打包场景链路参数
    """
    links = []
    # 网络接口和网卡的创建
    for sqllink in sqllinks:
        iface_helper = client.InterfaceHelper(
            ip4_prefix=sqllink["networkv4"], ip6_prefix=sqllink["networkv6"])
        iface1, iface2 = None, None
        if sqllink["iface1"]:
            [host, eth] = sqllink["iface1"].split(':')
            iface1 = iface_helper.create_iface(int(host), int(eth))
        if sqllink["iface2"]:
            [host, eth] = sqllink["iface2"].split(':')
            iface1 = iface_helper.create_iface(int(host), int(eth))
        type = core_pb2.LinkType.WIRED
        if sqllink["type"] != 1:
            type = core_pb2.LinkType.WIRELESS
        options = core_pb2.LinkOptions(
            delay=sqllink["delay"],
            bandwidth=sqllink["bandwidth"],
            loss=sqllink["loss"],
            mer=sqllink["mer"],
            buffer=sqllink["buffer"],
            key=sqllink["key"],)

        link = core_pb2.Link(node1_id=sqllink["node1_id"],
                                node2_id=sqllink["node2_id"],
                                type=type,
                                iface1=iface1,
                                iface2=iface2,
                                options=options,)
        links.append(link)
    return links
    

def pack_svss(sqlsvss):
    """
    打包服务和服务文件参数
    """
    service_configs = []
    service_file_configs = []
    for sqlsvs in sqlsvss:
        directories = []
        if sqlsvs["directories"]:
            directories = sqlsvs["directories"].split(';')
        files = []
        if sqlsvs["files"]:
            files = sqlsvs["files"].split(';')
        startup = []
        if sqlsvs["startup"]:
            startup = sqlsvs["startup"].split(';')
        validate = []
        if sqlsvs["validate"]:
            validate = sqlsvs["validate"].split(';')
        shutdown = []
        if sqlsvs["shutdown"]:
            shutdown = sqlsvs["shutdown"].split(';')
        service_config = ServiceConfig(
            node_id = sqlsvs["node_id"],
            service = sqlsvs["service_kind"],
            directories = directories,
            files = files,
            startup = startup,
            validate = validate,
            shutdown = shutdown,
        )
        service_configs.append(service_config)
        if sqlsvs["data"]:
            i = 0
            for da in sqlsvs["data"].split(';'):
                service_file_config = ServiceFileConfig(
                    node_id = sqlsvs["node_id"],
                    service = sqlsvs["service_kind"],
                    file = files[i],
                    data = da,
                )
                i += 1
                service_file_configs.append(service_file_config)
    return (service_configs, service_file_configs)


def Created_Session(msg):
    """ 
    创建会话并返回会话id
    """
    try:
        response = core.create_session()
    except grpc.RpcError as e:
        details = e.details()
        logger.error("error details:{details}")
        return {"flag": False, "details": details, }
    session_id = response.session_id
    logger.info(f"创建会话 {session_id}")
    msg = {'flag': True, 'session_id': session_id}
    return msg


def Start_Session(msg):
    """ 
    解析对应会话的数据库，并实例化运行仿真
    具体参数执行逻辑参照 excel 和 sql
    """
    try:
        session_id = msg["session_id"]
        (sqlnodes, sqllinks, sqlsvss, sqlconfig) = nest_data.parse(session_id)
        core.set_session_state(session_id, SessionState.CONFIGURATION)

        nest_config = pack_config(session_id, sqlconfig)
        nest_nodes = pack_nodes(sqlnodes)
        nest_links = pack_links(sqllinks)
        nest_svss = pack_svss(sqlsvss)

        # 各节点中对emane的配置,此处先固定默认参数
        model_configs = []
        for node in nest_nodes:
            if node.emane:
                model_config = EmaneModelConfig(
                    node_id=node.id,
                    iface_id=-1,
                    model=node.emane,
                )
                model_configs.append(model_config)

        core.start_session(
            session_id,
            nest_nodes,
            nest_links,
            location = nest_config[0],
            hooks = nest_config[1],
            emane_config = nest_config[2],
            emane_model_configs=model_configs,
            # wlan_configs = wlan_configs,
            # mobility_configs = mobility_configs,
            service_configs = nest_svss[0],
            service_file_configs = nest_svss[1],
            # config_service_configs = config_service_configs,
        )
        core.save_xml(session_id, os.path.join(
            scenario_path, f"test{session_id}.xml"))    # 保存场景备份
    except grpc.RpcError as e:
        details = e.details()
        logger.error(f"error details:{details}")
        return {"flag": False, "details": details}
    logger.info(f"会话{session_id}执行成功")
    return {'session_id': session_id, 'flag': True}


def Run_Node_Cmd(msg):
    """
    发送运行节点cmd的指令的语句
    :param session_id: 会话id
    :param node_id: 节点 id
    :param cmd: 执行语句
    :param wait: 是否堵塞等待语句执行完成
    :return: 执行成功flag, 终端输出output，命令返回值return_code
    :raises grpc.RpcError:当节点不存在
    """
    try:
        # response = core.get_node_terminal(msg["session_id"], 1)
        # print(response.terminal) 返回终端cmd命令
        response = core.node_command(
            msg["session_id"],
            msg["nodeid"],
            msg["cmd"],
            wait=msg["wait"])
        msg = {
            "flag": True,
            "output": response.output,
            "return_code": response.return_code,
        }
        # print(response.output, response.return_code, sep='\n')
    except grpc.RpcError as e:
        details = e.details()
        logger.error(f"error details:{details}")
        return {"flag": False, "details": details}
    return msg


def Stop_Session(msg):
    """
    停止指定的会话
    :param session_id: 会话id
    :return: flag 表示是否成功执行
    """
    try:
        response = core.stop_session(msg["session_id"])
        response = core.delete_session(msg["session_id"])  # 删除对应会话
    except grpc.RpcError as e:
        details = e.details()
        logger.error("error details:{details}")
        return {"flag": False, "details": details}
    # 删除对应数据库数据
    nest_data.delete(msg["session_id"])
    logger.info(f"停止并删除会话 {msg['session_id']}")
    return {"flag": response.result}


def Open_Session(msg):
    """
    后台运行指定场景
    :param filepath: 场景路径
    :return: flag 表示是否成功执行
    """
    filepath = msg["filepath"]
    try:
        response = core.open_xml(filepath, True)
    except grpc.RpcError as e:
        details = e.details()
        logger.error(f"error details:{details}")
        return {"flag": False, "details": details}
    except FileNotFoundError:
        logger.error(f"error details:{filepath} not find")
        return {"flag": False, "details": "FileNotFoundError"}
    logger.info(f"执行场景{filepath}成功, 仿真会话为 {response.session_id}")
    return {'session_id': response.session_id, 'flag': response.result}


def Get_Sessions(msg):
    """
    显示仿真平台全部会话
    """
    response = core.get_sessions()
    states = (
        "UNKNOWN",
        "DEFINITION",
        "CONFIGURATION",
        "INSTANTIATION",
        "RUNTIME",
        "DATACOLLECT",
        "SHUTDOWN",
    )
    sessions = []
    for res in response.sessions:
        s = {
            "id": res.id,
            "state": states[res.state],
            "nodes": res.nodes,
            "file": res.file,
            "dir": res.dir,
        }
        sessions.append(s)
    return sessions


Instructions = {
    Instr.created_session: Created_Session,
    Instr.start_session: Start_Session,
    Instr.run_node_cmd: Run_Node_Cmd,
    Instr.stop_session: Stop_Session,
    Instr.open_session: Open_Session,
    Instr.get_sessions: Get_Sessions,
}


def resolve(msg):
    if(type(msg) != dict):  # 暂时不考虑发送的json列表，仅处理列表第一个
        msg = msg[0]
    callback = Instr.get(msg['instr'])
    if callback is None:
        logger.error(f"invaild instructions{msg}")
        return
    callback = Instructions[callback]
    return callback(msg)


if __name__ == "__main__":
    msg1 = [{'timestamp': "1", 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
            'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"},
            {'timestamp': "1", 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
            'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"}]

    msg = {'instr': 6, 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
           'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"}
    msg = json.dumps(msg)
    # print(msg, type(msg))
    msg = json.loads(msg)
    # print(msg, type(msg))
    resolve(msg)
    core.close()
