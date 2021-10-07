#!/usr/bin/python3
import re
import psutil

def get_netcard(ethname: str):
    # 取所有网卡ipv4 ip
    netcard_info = []
    info = psutil.net_if_addrs()
    for k, v in info.items():
    # k是接口名，v是该接口全部ip地址
        if(k != ethname):
            continue
        for item in v:
            if item[0] == 2 and not item[1] == '127.0.0.1':
                netcard_info.append((k, item[1]))
    return netcard_info

def setNode() -> None :
    # 读取nem配置文件 取出 nemid[&nodeid]="&eth &nemid" 这样格式的字典
    with open('/tmp/pycore.33987/emane_nems', 'r', encoding='utf-8') as emane_nems:
        nemid = {}
        nems = emane_nems.readlines()
        for nem in nems:
            re_nem = re.match(r'(n\d+ eth\d+) (\d+)', nem)
            nemid[re_nem.group(1)]=re_nem.group(2)

    # 取出所有节点中使用了CRradio模型的网卡
    CRradio_model = ''
    with open('mytest_emane_CRradio.imn', 'r', encoding='utf-8') as config :
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
        return
    print(interface[CRradio_model])
    # interface[(CRradio_model)] interface字典对应列表为 nodeid eth类型
    for nodes in interface[CRradio_model] :
        node=nodes.split(' ')
        # logging.info(
        #     "setting up CRradio tdma schedule: schedule(%s) device(%s)", schedule, event_device
        # )
        # args = f"coresendmsg -i {event_device} {schedule}"
        print(f'coresendmsg execute node={node[0][1:]} number=1001 command="/home/lk233/gopl.io/Nodes_multicast {node[1]} {nemid[nodes]}"')

if __name__ == "__main__" :
    # setNode()
    print(get_netcard('ens33'))
    # event_deviceIP = "LKtest ctrl0.1b: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu 1500\
    #     inet 172.16.0.254  netmask 255.255.255.0  broadcast 0.0.0.0\
    #     inet6 fe80::78f1:c0ff:fe66:ab25  prefixlen 64  scopeid 0x20<link>\
    #     ether 0a:74:1a:dc:78:a8  txqueuelen 1000  (以太网)\
    #     RX packets 238  bytes 24644 (24.6 KB)\
    #     RX errors 0  dropped 0  overruns 0  frame 0\
    #     TX packets 168  bytes 14852 (14.8 KB)\
    #     TX errors 0  dropped 0 overruns 0  carrier 0  collisions 0"
    # print(f'LKtest {event_deviceIP}')
    # print(f'LKtest {event_deviceIP}')
    # event_deviceIP = "inet 172.16.0.254  netmask 255.255.255.0  broadcast 0.0.0.0"
    # event_deviceIP = event_deviceIP.split('\n')[1]
    # event_deviceIP = re.match(r'inet (\d+\.\d+\.\d+\.\d+)', event_deviceIP)
    # event_deviceIP = event_deviceIP.group(1)
    # print(f'LKtest {event_deviceIP}')
