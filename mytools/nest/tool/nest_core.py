"""
包含了对 json 包的解析与处理
并且实现了对 core grpc api 的仿真器调用
指令统一使用json封装，下面是具体细节
"""

from core.api.grpc import client, core_pb2
from core.api.grpc.wlan_pb2 import WlanConfig
from core.api.grpc.emane_pb2 import EmaneModelConfig
from core.api.grpc.core_pb2 import Node, Geo, Position, SessionState
from core.api.grpc.mobility_pb2 import MobilityAction, MobilityConfig
from core.api.grpc.services_pb2 import ServiceAction, ServiceConfig, ServiceFileConfig
from core.emane import emanemodel
from core.nodes.network import SwitchNode, WlanNode
from core.emulator.enumerations import LinkTypes, NodeTypes

from enum import Enum, unique

from sql import nest_data
from tool import tlv_apimsg
from tool.mylog import logger, scenario_path, Nest_path
from threading import Timer
import grpc
import json, csv
import os, datetime


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
AllTimer = {}  # 所有会话的循环定时器字典
gps_path:str = os.path.join(nest_data.f["gps_link_path"], "TMP") + '/zLEO_LLAXYZ'
link_path:str = os.path.join(nest_data.f["gps_link_path"], "zAllLinks") + '/zAllLinks'

linkmap = {} # 全局link表字典
emanemap = {} # 全局emane链接表字典

@unique
class Instr(Enum):
    created_session = 1
    start_session = 2
    run_node_cmd = 3
    stop_session = 4
    open_session = 5
    get_sessions = 6
    Flow_Data = 1000

    @classmethod
    def get(cls, name: str) -> "Instr":
        try:
            return Instr(name)
        except ValueError:
            return None


def pack_config(session_id, sqlconfig):
    """
    打包各项系统参数，系统配置表必须存在
    """
    # 设定控制网
    sql_config = sqlconfig[0]
    if sql_config["Ctrlnet0"]:
        core.set_session_options(session_id,{"controlnet0" : sql_config["Ctrlnet0"]})
    if sql_config["Ctrlnet1"]:
        core.set_session_options(session_id,{"controlnet1" : sql_config["Ctrlnet1"]})
    hooks, emane_config = [], {}
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
    if sql_config["hook"]:
        hook1=sql_config["hook"].split(";")
        for hook2 in hook1:
            temp=hook2.split(":")
            hook = core_pb2.Hook(
                state=int(temp[0]), file=temp[1], data=temp[2]
            )
            hooks.append(hook)
    # 总体系统参数的emane配置
    if sql_config["emane_config"]:
        temp=sql_config["emane_config"].split(";")
        for temp1 in temp:
            temp2=temp1.split(":")
            emane_config[temp2[0]] = temp2[1]
    return (location, hooks, emane_config)


def pack_nodes(session_id, sqlnodes):
    """
    打包场景节点参数
    """
    nodes = []
    if not sqlnodes:
        logger.warning(f"会话 {session_id} 节点 配置表不存在")
        return nodes
    for sql_node in sqlnodes:
        xyz, lla, model, emane_mod = None, None, None, None
        if sql_node["position"]:
            xyz = sql_node["position"].split()
            xyz = Position(x=float(xyz[0]), y=float(xyz[1]), z=float(xyz[2]))
        if sql_node["geo"]:
            lla = sql_node["geo"].split()
            lla = Geo(lat=float(lla[0]), lon=float(lla[1]), alt=float(lla[2]))
        if not sql_node['model'] is None:
            model = nodemodel[sql_node['model']]
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
            position=xyz,
            geo=lla,      
            type=sql_node['types'],
            model=model,
            emane=emane_mod,
            services=services,
            server=sql_node["distribute"],
        )
        nodes.append(NN)
    return nodes


def pack_links(session_id, sqllinks):
    """
    打包场景链路参数
    iface1 2 为中间生成的临时网络接口
    links为最后生成数据 iface为相邻链路数据用于生成拓扑信息
    """
    links, ifaces = [], []
    node_eth={}
    if not sqllinks:
        logger.warning(f"会话 {session_id} 链路 配置表不存在")
        return links
    # 网络接口和链路的创建
    for sqllink in sqllinks:
        iface_helper = client.InterfaceHelper(
            ip4_prefix=sqllink["networkv4"], ip6_prefix=sqllink["networkv6"])
        iface1, iface2 = None, None

        # swy
        temp_iface = [sqllink["node1_id"], "", "", sqllink["node2_id"], "", ""]
        if not sqllink["iface1"] is None:
            host = sqllink["iface1"]
            if sqllink["node1_id"] in node_eth:
                node_eth[sqllink["node1_id"]] += 1
            else:
                node_eth[sqllink["node1_id"]] = 0
            if not host:
                host = sqllink["node1_id"]
            iface1 = iface_helper.create_iface(int(host), node_eth[sqllink["node1_id"]])
            temp_iface[1] = f'eth{node_eth[sqllink["node1_id"]]}'
            temp_iface[2] = f'{iface1.ip4}'
        if not sqllink["iface2"] is None:
            host = sqllink["iface2"]
            if sqllink["node2_id"] in node_eth:
                node_eth[sqllink["node2_id"]] += 1
            else:
                node_eth[sqllink["node2_id"]] = 0
            if not host:
                host = sqllink["node2_id"]
            iface2 = iface_helper.create_iface(int(host), node_eth[sqllink["node2_id"]])
            temp_iface[4] = f'eth{node_eth[sqllink["node2_id"]]}'
            temp_iface[5] = f'{iface2.ip4}'
        ifaces.append(temp_iface) 
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
    if ifaces:
        emanelinkmap(session_id, ifaces)
        # nest_data.mysql_cmd( # 放弃写入数据库
        #     f"CREATE TABLE IF NOT EXISTS session_{session_id}_iface LIKE session_template_iface")
        # nest_data.mysql_cmd(f"DELETE FROM session_{session_id}_iface")
        # sql=f'INSERT INTO session_{session_id}_iface(node1_id,node1_eth,node1_ip,node2_id,node2_eth,node2_ip) VALUES (%s,%s,%s,%s,%s,%s)'
        # nest_data.mysql_cmd2(sql,ifaces)
        # topology_generator(ifaces) # 计算拓扑 废弃
    return links
    

def pack_svss(session_id, sqlsvss):
    """
    打包服务和服务文件参数
    """
    service_configs = []
    service_file_configs = []
    if not sqlsvss:
        logger.warning(f"会话 {session_id} 服务 配置表不存在")
        return (service_configs, service_file_configs)
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


def pack_emanes(session_id, sqlemanes, nest_nodes):
    """
    打包无线配置参数
    """
    emane_configs = []
    if not sqlemanes:
        logger.warning(f"会话 {session_id} emane 配置表不存在")
        # 云节点的emane配置 使用节点参数模型
        for node in nest_nodes:
            if node.emane:
                model_config = EmaneModelConfig(
                    node_id=node.id,
                    iface_id=-1,
                    model=node.emane,
                    config={"txpower":"10000",
                            "fixedantennagain":"1230"},
                )
                emane_configs.append(model_config)
        return emane_configs
    for sqlemane in sqlemanes:
        nodeid = sqlemane["nodeid"]
        configs = {}
        if sqlemane["configs"]:
            temps = sqlemane["configs"].split(';')
            for temp in temps:               
                configs[temp.split(':')[0]] = temp.split(':')[1]
        logger.debug(f"{configs}")
        
        model = Emanemodel[sqlemane["model"]]  
        ifaceid = sqlemane["ifaceid"]
        emane_config = EmaneModelConfig(
                        node_id=nodeid,
                        iface_id=ifaceid,
                        model=model,
                        config=configs,
                    )

        emane_configs.append(emane_config)
    return emane_configs


def Created_Session(msg):
    """ 
    创建会话并返回会话id
    """
    try:
        response = core.create_session()
    except grpc.RpcError as e:
        details = e.details()
        logger.error(f"error details:{details}")
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
        logger.info(f"读取配置参数，并实例化会话 {session_id} 场景")
        (sqlnodes, sqllinks, sqlsvss, sqlemanes, sqlconfig) = nest_data.parse(session_id)
        core.set_session_state(session_id, SessionState.CONFIGURATION)

        nest_config = pack_config(session_id, sqlconfig)
        nest_nodes = pack_nodes(session_id, sqlnodes)
        nest_links = pack_links(session_id, sqllinks)
        nest_svss = pack_svss(session_id, sqlsvss)
        nest_emanes = pack_emanes(session_id, sqlemanes, nest_nodes)

        core.start_session(
            session_id,
            nest_nodes,
            nest_links,
            location = nest_config[0],
            hooks = nest_config[1],
            emane_config = nest_config[2],
            emane_model_configs = nest_emanes,
            # wlan_configs = wlan_configs,
            # mobility_configs = mobility_configs,
            service_configs = nest_svss[0],
            service_file_configs = nest_svss[1],
            # config_service_configs = config_service_configs,
        )
        core.save_xml(session_id, os.path.join(
            scenario_path, f"test{session_id}.xml"))    # 保存场景备份
        nest_data.set_status(session_id, 4)
        # gps_link_init(session_id)   # 动态链路 gps 初始化
        # MyTimer(1, 8, 10, session_id)   # 启动定时器
        ClearFlowData()
        Get_Flow(session_id)
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
        # logger.info(response.terminal) 返回终端cmd命令
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
        # logger.info(response.output, response.return_code, sep='\n')
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
        response = core.delete_session(msg["session_id"])  # 删除对应会话 关闭定时器
        if msg["session_id"] in AllTimer:
            AllTimer[msg["session_id"]].cancel()
            AllTimer.pop(msg["session_id"])
    except grpc.RpcError as e:
        details = e.details()
        logger.error(f"error details:{details}")
        return {"flag": False, "details": details}
    # 删除对应数据库数据
    # nest_data.delete(msg["session_id"])
    # logger.info(f"停止并删除会话 {msg['session_id']}")
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


def ClearFlowData():
    data_statistics = ['delayjitter','enddelay','gencetime','lossrate','outandrece','receive','sendingrate','timingthroughput','transmit','utilratio']
    for table in data_statistics:
        sql = f"DELETE FROM process_{table}"
        nest_data.mysql_cmd(sql)


def Flow_Data(msg):
    simulation_time = str(datetime.datetime.now())
    flow_id = msg.get('flow_id')
    delayjitter = msg.get('delayjitter')
    lossrate = msg.get('lossrate')
    sendingrate = msg.get('sendingrate')
    # 发送数据量
    dr_num = msg.get['transmits']

    if delayjitter:
        sql = f"INSERT INTO process_delayjitter(id,flow_id,delayjitter) VALUES({flow_id},{flow_id},'{delayjitter}') ON DUPLICATE KEY UPDATE delayjitter='{delayjitter}'"
        nest_data.mysql_cmd(sql)
        logger.debug(sql)
    if lossrate:
        sql = f"INSERT INTO process_lossrate(id,flow_id,lossrate) VALUES({flow_id},{flow_id},'{lossrate}') ON DUPLICATE KEY UPDATE lossrate='{lossrate}'"
        nest_data.mysql_cmd(sql)
        logger.debug(sql)
        if dr_num:
            # 接受数据量
            value = f'{int(dr_num.split()[0]) * (1 - float(lossrate[0]))} {dr_num.split()[1]}'
            sql = f"INSERT INTO process_timingthroughput(id,sid,simulation_time,throughput) VALUES({flow_id},{flow_id},'{simulation_time}','{dr_num}') ON DUPLICATE KEY UPDATE simulation_time='{simulation_time}',throughput='{dr_num}'"
            nest_data.mysql_cmd(sql)
            logger.debug(sql)
            sql = f"INSERT INTO process_outandrece(id,sid,flow_id,dr_num,value) VALUES({flow_id},{flow_id},{flow_id},'{dr_num}','{value}') ON DUPLICATE KEY UPDATE dr_num='{dr_num}',value='{value}'"
            logger.debug(sql)
            nest_data.mysql_cmd(sql)
    if sendingrate:
        sql = f"INSERT INTO process_sendingrate(id,sid,simulation_time,sendingrate) VALUES({flow_id},{flow_id},'{simulation_time}','{sendingrate}') ON DUPLICATE KEY UPDATE simulation_time='{simulation_time}',sendingrate='{sendingrate}'"
        nest_data.mysql_cmd(sql)
        logger.debug(sql)

    return None


def Nodes_Mobility(session_id, filepath):
    """
    读取对应文件动态移动场景节点
    """
    with open(filepath) as positions:
        positions = csv.reader(positions)
        next(positions)
        for position in positions:
            nodeid = int(position[0])
            lat = float(position[7])
            lon = float(position[8]) - 180.0
            alt = float(position[9]) * 1000
            geo = Geo(lat=lat, lon=lon, alt=alt)
            logger.info(f"会话{session_id} 节点{nodeid}, {geo}")
            response = core.edit_node(session_id, nodeid, geo=geo)
            if (not response.result):
                logger.warning('set postion fault')


def Links_Mobility(session_id, filepath, optition):
    with open(filepath) as positions:
        positions = csv.reader(positions)
        next(positions)
        for position in positions:
            if position[4] == "1" or position[4] == "3":
                # optition = position[4]
                user_id = int(position[0])
                satellite_id = int(position[2] )
                logger.info(f"会话{session_id}, 地面节点{user_id}, 卫星节点{satellite_id}, 选项{optition}")
                match(session_id, user_id, satellite_id, optition)


def gps_link_init(session_id):
    """ 将所有无线网 断开,初始化仿真节点经纬高 """
    sql = f'SELECT * FROM session_{session_id}_iface'
    temp_data = nest_data.mysql_cmd1(sql,True)
    for i in temp_data:
        if i['node2_eth']=='':
            core.node_command(session_id,i['node1_id'],f"ip link set {i['node1_eth']} down",False)
            logger.debug(f"会话{session_id}, 节点id{i['node1_id']}, 初始化失效网卡{i['node1_eth']}")
    Links_Mobility(session_id, f"{link_path}-00000.csv", 'init')
    Nodes_Mobility(session_id, f"{gps_path}-00000.csv")


# def Modify_Link(session_id,node1_id,node1_eth,node2_id,node2_eth,optition):
#     """    
#     node1_eth:节点1的网卡
#     node2_eth:节点2的网卡
#     optition:控制网卡up或down 
#     """
#     if node2_eth == '':
#         core.node_command(session_id,node1_id,f"ip link set {node1_eth} {optition}")
#     else :
#         core.node_command(session_id,node1_id,f"ip link set {node1_eth} {optition}")
#         core.node_command(session_id,node2_id,f"ip link set {node2_eth} {optition}")


def match(session_id,node1_id,node2_id,optition):
    """
    node1_id:需要建立连接的用户节点
    node2_id:需要建立连接的卫星节点
    """
    sql = f'SELECT * FROM `session_{session_id}_links` WHERE node1_id = {node1_id} and iface2  is NULL'
    temp_data = nest_data.mysql_cmd1(sql,True)
    # 得到用户所连接的无线云的节点号
    temp_node_wlan = temp_data[0]['node2_id']

    # 得到用户对应的卫星节点信息
    sql = f"SELECT * FROM `session_{session_id}_iface` WHERE node2_id = {temp_node_wlan} and node1_id ={node2_id} limit 1 "
    temp_data_satellite = nest_data.mysql_cmd1(sql,True)
    
    # 得到用户对应的云节点信息
    sql = f"SELECT * FROM `session_{session_id}_iface` WHERE node2_id = {temp_node_wlan} and node1_id ={node1_id} limit 1 "
    temp_data_user = nest_data.mysql_cmd1(sql,True)

    if (optition != 'init') :
        core.node_command(session_id,temp_data_satellite[0]['node1_id'],f"ip link set {temp_data_satellite[0]['node1_eth']} {optition}")
    else :
        optition = "up"
        core.node_command(session_id,temp_data_satellite[0]['node1_id'],f"ip link set {temp_data_satellite[0]['node1_eth']} {optition}")
        core.node_command(session_id,temp_data_user[0]['node1_id'],f"ip link set {temp_data_user[0]['node1_eth']} {optition}")
        logger.info(f"会话{session_id} 地面节点{temp_data_user[0]['node1_id']} {temp_data_user[0]['node1_eth']} is {optition}")
    logger.info(f"会话{session_id} 卫星节点{temp_data_satellite[0]['node1_id']} {temp_data_satellite[0]['node1_eth']} is {optition}")

def emanelinkmap(session_id, ifaces):
    """
    :param ifaces: 链路信息列表iface 输入类似
    [12, 'eth1', '10.0.1.1', 23, 'eth0', '10.0.1.2']
    输出 下面两个字典存储在全局的字典中 linkmap emanemap
    ifmap-> key: (节点id1 节点id2) 元祖   value: (节点1网卡 节点1ip 节点2网卡 节点2ip) 元祖
    emmap-> key: 终端节点id alue: (云节点id 终端ip) 元祖
    """
    ifmap, emmap = {}, {}
    for iface in ifaces:
        ifmap[(iface[0], iface[3])] = (iface[1], iface[2], iface[4], iface[5])
        if(not iface[4]):
            if(iface[0] in emmap):
                emmap[iface[0]] = None
            else:
                emmap[iface[0]] = (iface[3], iface[2])
    for key in emmap.copy(): # 由于卫星节点重复出现会被标记为none，删除之 注意需要用备份字典进行遍历
        if(emmap[key] is None):
            del emmap[key]
    linkmap[session_id] = ifmap
    emanemap[session_id] = emmap
    # print(ifmap)
    # print(emmap)


def topology_generator(ifaces):
    """
    :param ifaces: 链路信息列表iface 输入类似
    [12, 'eth1', '10.0.1.1', 23, 'eth0', '10.0.1.2']
    假设目前所有有线链路为卫星链路，且按照先 同轨后相异轨的形式拼接
    输出对应拓扑文件, 之后计算 终端 到 关口站 无线路由
    """
    logger.info(ifaces)
    topo, temptopo = [], [] # 二维拓扑表 临时轨道表
    myset = set() # 二维列表 所有元素的set 单个轨道内的set
    ifaceip = {} # key为节点id元祖 value对应ip元祖 哈希表  注意:节点对未查询到需要逆转查询
    for iface in ifaces:
        ifaceip[(iface[0], iface[3])] = (iface[2], iface[5])
        print((iface[0], iface[3]))
        if (not iface[1]) or (not iface[4]): # 略过无线云
            # print(ifaceip[(iface[0], iface[3])])
            continue
        # 建立拓扑思路：建立所有轨道，确保输入的异轨间链路与输入同轨节点顺序相同
        if ((not iface[0] in myset) or (not iface[3] in myset)):
            if (not temptopo):
                temptopo = [iface[0], iface[3]]
            else: # 拼接同轨
                temp = iface[0] if iface[0] not in myset else iface[3]
                temptopo.append(temp)
            myset.update((iface[0], iface[3]))
        else: # temptopo有数据代表同轨建立完毕, 否则是异轨
            if(temptopo):
                topo.append(temptopo)
                temptopo = []
            else: #跳过异轨间处理
                pass

    

def Get_Flow(session_id):
    table = f"session_{session_id}_flows"
    sql = f'SELECT * FROM {table}'
    flows = nest_data.mysql_cmd1(sql,True)
    for flow in flows:
        flow_id = flow.get('flow_id')
        bandwidth = flow.get('bandwidth')
        if flow.get('src_id') and flow.get('dst_id'):
            src_id = flow.get('src_id')
            dst_id = flow.get('dst_id')
            #查节点第一个ipv4 的ip
            response = core.get_node(session_id, dst_id)
            if response.ifaces:
                for net in response.ifaces:
                    if(net.name == 'eth0'):
                        dst_ip = net.ip4
                # dst_ip = response.ifaces[-2].ip4
                logger.debug(dst_ip)
                core.node_command(session_id, dst_id, 'iperf3 -s', False)
                core.node_command(session_id, src_id, f'core-python {Nest_path}/temp/iperf3_client.py {flow_id} {dst_ip} 1000 {bandwidth}',False)
            else:
                return


def MyTimer(count, maxn, interval, session_id):
    """
    子线程定时器不会接收到父线程 interrupt 需要父进程关闭
    类似文件未找到 节点不存在grpc等错误仅跳过该错误不做处理
    :param count: 当前计数值
    :param maxn: 最大次数，总循环次数为 count初始值 至 maxn-1
    :param interval: 间隔时间
    :param session_id: 会话id
    """
    try:
        # 切换路由太慢 所以每四次count才切换
        last = maxn-4 if count-4 < 0 else count-4
        last = '%05d' % (last*60)
        temp = '%05d' % (count*60)
        logger.info(f"会话{session_id} 计时器last {last}, now {count}")
        Nodes_Mobility(session_id, f"{gps_path}-{temp}.csv")
        if(count % 4 == 0):
            Links_Mobility(session_id, f"{link_path}-{last}.csv", 'down')
            Links_Mobility(session_id, f"{link_path}-{temp}.csv", 'up')
    except grpc.RpcError as e:
        logger.error(e.details())
    except Exception as e:
        logger.error(e)
    count += 1
    if count >= maxn:
        # 临时改为无限循环
        count = 0 
    AllTimer[session_id] = Timer(interval, MyTimer, args=[count, maxn, interval, session_id])
    AllTimer[session_id].start()


Instructions = {
    Instr.created_session: Created_Session,
    Instr.start_session: Start_Session,
    Instr.run_node_cmd: Run_Node_Cmd,
    Instr.stop_session: Stop_Session,
    Instr.open_session: Open_Session,
    Instr.get_sessions: Get_Sessions,
    Instr.Flow_Data: Flow_Data,
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


# if __name__ == "__main__":
#     msg1 = [{'timestamp': "1", 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
#             'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"},
#             {'timestamp': "1", 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
#             'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"}]

#     msg = {'instr': 6, 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
#            'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"}
#     msg = json.dumps(msg)
#     # print(msg, type(msg))
#     msg = json.loads(msg)
#     # print(msg, type(msg))
#     resolve(msg)
#     core.close()
