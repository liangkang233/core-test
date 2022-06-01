"""
custom CRradio emane model by LK233.
"""
from typing import Dict, List, Optional, Set

from core import utils
from core.config import Configuration
from core.emane import emanemanifest, emanemodel
from core.emulator.enumerations import ConfigDataTypes

import re, psutil
import os
import logging


class CRradioModel(emanemodel.EmaneModel):
    
    # model name
    name: str = "emane_CRradio"

    # phy configuration
    # phy_library: Optional[str] = None
    phy_xml: str = "/usr/share/emane/manifest/emanephy.xml"
    phy_defaults: Dict[str, str] = {
        "subid": "7",
        "noisemode": "all",
        "propagationmodel": "2ray",
        "txpower": "5.0",
        "bandwidth": "8000000",
        "systemnoisefigure": "4.0",
    }

    # mac configuration
    # mac_library: str = "CRradio"
    mac_library: str = "tdmaeventschedulerradiomodel"
    mac_xml: str = "/usr/share/emane/manifest/CRradio.xml"
    mac_defaults: Dict[str, str] = {
        "pcrcurveuri": "/usr/share/emane/xml/models/mac/CRradioscheduler/CRradiopcr.xml"
    }

    # add custom schedule options and ignore it when writing emane xml
    schedule_name: str = "schedule"
    default_schedule: str = os.path.expandvars('$HOME') + "/.core/configs/configuration/schedule.xml"
    # 添加自定义多播程序选项
    Multicast_name: str = "Nodes_multicast"
    default_multicast: str = os.path.expandvars('$HOME') + "/.core/configs/configuration/Nodes_multicast"
    
    config_ignore: Set[str] = {schedule_name, Multicast_name}


    @classmethod
    def load(cls, emane_prefix: str) -> None:
        # super().load(emane_prefix)
        cls.phy_config: List[Configuration] = emanemanifest.parse(cls.phy_xml, cls.phy_defaults)
        cls.mac_config: List[Configuration] = emanemanifest.parse(cls.mac_xml, cls.mac_defaults)

        cls.mac_config.insert(
            0,
            Configuration(
                _id=cls.schedule_name,
                _type=ConfigDataTypes.STRING,
                default=cls.default_schedule,
                label="CRradio schedule file",
            ),
        )
        cls.mac_config.insert(
            1,
            Configuration(
                _id=cls.Multicast_name,
                _type=ConfigDataTypes.STRING,
                default=cls.default_multicast,
                label="node send multicast file(Schedule_update must in the same directory)",
            ),
        )

    def post_startup(self) -> None:
        # Logic to execute after the emane manager is finished with startup.
        # :return: nothing

        # get configured schedule
        config = self.session.emane.get_configs(node_id=self.id, config_type=self.name)
        if not config:
            return
        schedule = config[self.schedule_name]
        Nodes_multicast = config[self.Multicast_name]

        # get the set event device
        event_device = self.session.emane.event_device


        # initiate tdma schedule
        logging.info(
            "setting up CRradio tdma schedule: schedule(%s) device(%s)", schedule, event_device
        )
        args = f"emaneevent-tdmaschedule -i {event_device} {schedule}"
        utils.cmd(args)
        
        # 设置各个节点多播程序Nodes_multicast,并发送至event_deviceIP
        self.Nodes_multicast(Nodes_multicast, event_device)
        # 启动动态时隙整合程序  注意:时隙文件中的nodes指的是nemid,非nodeid,也不是节点hostname
        path=os.path.split(Nodes_multicast)[0]
        utils.mute_detach(f"{path}/Schedule_update {event_device} {schedule}")
        logging.info('setting up CtrlNet:"%s", load schedule config:"%s"', event_device, schedule)

    def Nodes_multicast(self, Nodes_multicast: str, event_device: str) -> None:
        # 读取nem配置文件 取出 nemid[&nodeid]="&eth &nemid" 这样格式的字典
        with open(self.session.session_dir+'/emane_nems', 'r', encoding='utf-8') as emane_nems:
            nemid = {}
            nems = emane_nems.readlines()
            for nem in nems:
                nem = re.match(r'(n\d+ eth\d+) (\d+)', nem)
                nemid[nem.group(1)]=nem.group(2)

        # 读取场景配置文件取出使用了CRradio模型的所有节点的网卡
        # 生成类似字典 n17 为云节点id {'n17': ['n2 eth0', 'n3 eth0', 'n4 eth0', 'n5 eth0', 'n6 eth0', 'n7 eth0', 'n8 eth0', 'n9 eth0', 'n10 eth0', 'n11 eth0', 'n12 eth0', 'n13 eth0', 'n14 eth0', 'n15 eth0', 'n16 eth0', 'n1 eth0'], 'n2': ['n17 e0'], 'n3': ['n17 e1'], 'n4': ['n17 e2'], 'n5': ['n17 e3'], 'n6': ['n17 e4'], 'n7': ['n17 e5'], 'n8': ['n17 e6'], 'n9': ['n17 e7'], 'n10': ['n17 e8'], 'n11': ['n17 e9'], 'n12': ['n17 e10'], 'n13': ['n17 e11'], 'n14': ['n17 e12'], 'n15': ['n17 e13'], 'n16': ['n17 e14'], 'n1': ['n17 e15']}
        CRradio_model = ''
        with open(self.session.file_name, 'r', encoding='utf-8') as config :
            interface = {}
            lines = config.readlines()
            for line in lines:
                if line.startswith("node") :
                    id = line.split(' ')[1]
                elif re.match(r'\s+interface-peer', line):
                    netinfo = re.split(r"\s+", line)
                    if interface.get(netinfo[3][:-1]) == None : #第一次访问该key初始化一个列表
                        interface[netinfo[3][:-1]] = [id + ' ' + netinfo[2][1:]]
                    else :
                        interface[netinfo[3][:-1]].append(id + ' ' + netinfo[2][1:])
                elif re.match(r'\s+emane_CRradio', line):
                    CRradio_model=id
                else :
                    continue
        if interface.get(CRradio_model) == None :
            logging.warning("No interface found, no Nodes_multicast set up")
            return
        # 获取主控制网卡ip，用于各节点发送 "更新时隙"
        event_deviceIP = get_netcard(event_device)
        for nodes in interface[CRradio_model] :
            node=nodes.split(' ')
            #启动Nodes_multicast程序 形参分别为 网卡 nemid 控制网IP
            args = (f'coresendmsg execute node={node[0][1:]} number=1001 command="{Nodes_multicast} {node[1]} {nemid[nodes]} {event_deviceIP}"')
            utils.cmd(args) 
            logging.info("setting up CRradio tdma Nodes_multicast:%s\tinterface\t%s\tnemid:%s", node[0], node[1], nemid[nodes])

# 取网卡所有ipv4 ip
def get_netcard(ethname: str) -> str :
    info = psutil.net_if_addrs()
    for k, v in info.items():
    # k是接口名，v是该接口全部ip地址
        if(k != ethname):
            continue
        for item in v:
            if item[0] == 2 and not item[1] == '127.0.0.1':
                return item[1]
    return ""