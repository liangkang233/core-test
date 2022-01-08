import socket, sys
import time
from core import constants, utils
from core.errors import CoreCommandError
import json
import netifaces
import ipaddress
#主控网ip(ctrl0 ip) 端口
# command = 'ifconfig ctrl0 | grep inet'
# print(command)

res = netifaces.ifaddresses('ctrl0')[netifaces.AF_INET]
if res[0]:
    addr= res[0]["addr"]
    mask = res[0]["netmask"]
    parts = mask.split('.')
    mask_len = 0
    for part in parts:
        part = bin(int(part))
        for bit in part[2:]:
            if bit == '1':
                mask_len = mask_len + 1
    addr = addr + f'/{mask_len}'
    #####
    net = ipaddress.ip_network(addr, strict=False)
    HOST = str([x for x in net.hosts()][-1])
    print(HOST)
else:
    KeyboardInterrupt
# PORT = 5678
PORT = 5132
address = (HOST, PORT)

def main():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for i in range(int(sys.argv[3])):
        ip = sys.argv[2]
        # udp测试
        command = f"iperf3 -c {ip} -u -t 1s -b {sys.argv[4]} -f k"
        print(command)
        try:           
            trans = utils.cmd(command).split('\n')[-4]
            print(trans)
            tsplit = trans.split()
        except CoreCommandError as e:
            continue

        data = {
            'instr' : 1000,
            'flow_id':sys.argv[1],
            'delayjitter':tsplit[-4],
            'lossrate':tsplit[-1][1:-2],
            'sendingrate':f'{tsplit[6]} {tsplit[7]}',
            'transmits':f'{tsplit[4]} {tsplit[5]}'
        }
        command = f"ping {ip} -c 1"
        delays = utils.cmd(command).split('\n')[-1]
        delay = delays.split()[3][0:5] + ' ms'
        data['delay'] = delay
        # data['instr'] = 'Flow_Data'
        # data['flow_id'] = sys.argv[1]
        # data['delayjitter'] = tsplit[-4]  #抖动时延
        # data['lossrate'] = tsplit[-1][1:-2]   #丢包率
        # data['sendingrate'] = f'{tsplit[6]} {tsplit[7]}'   #发送速率            
        # data['transmits'] = f'{tsplit[4]} {tsplit[5]}'#传输数据量
        
        json_msg = json.dumps(data)
        print(json_msg)
        # send_data = ' '.join(data)
        
        udp_socket.sendto(json_msg.encode('utf-8'), address)

if __name__ == '__main__':
    main()

# coresendmsg execute flags=string,text node=2 number=1000 command='core-python /home/lk233/core/mytools/nest/temp/transdata.py 10 10.0.0.1 1 tcp'
# coresendmsg execute flags=string,text node=2 number=1000 command='core-python /home/hyh/core/nest/temp/iperf3_client.py {flow_id} {dst_ip} 10 {bandwidth}'
# core-python /home/hyh/core/nest/temp/iperf3_client.py 1 10.0.0.1 10 2M
# 1 10.0.0.1 10 2M 分别代表的含义为：业务id，目的IP，循环次数，带宽

