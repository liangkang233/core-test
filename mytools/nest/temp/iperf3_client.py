import socket, sys
import time
from core import constants, utils
from core.errors import CoreCommandError
#主控网ip 端口
HOST = '172.16.0.254'
PORT = 8081
address = (HOST, PORT)

def main():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    for i in range(int(sys.argv[1])):
        ip = sys.argv[2]
        if sys.argv[4] == 'udp':
            command = f"iperf3 -c {ip} -u -t 1s -b {sys.argv[5]} -f k"
        else:
            command = f"iperf3 -c {ip} -t 1s -f k"
        #print(command)
        try:
            res1 = utils.cmd(command).split('\n')[-4]
            split = res1.split()
        except CoreCommandError as e:
            # data = [sys.argv[3], '-1', '-1']
            # print(data)
            # send_data = ' '.join(data)
            # udp_socket.sendto(send_data.encode("utf-8"), address)
            continue
        data = []
        data.append(sys.argv[3])  #业务id
        if sys.argv[4] == 'udp':
            data.append(split[-1][1:-2])#丢包率
        else:
            data.append(split[8])#重传数

        data.append(split[6])   #流量
        data.append(sys.argv[4])   #协议类型
        # data.append(split[-4])  #抖动时延
        
        print(data)
        send_data = ' '.join(data)
        
        udp_socket.sendto(send_data.encode("utf-8"), address)

if __name__ == '__main__':
    main()

# coresendmsg execute flags=string,text node=2 number=1000 command='core-python /home/lk233/core/mytools/nest/temp/transdata.py 10 10.0.0.1 1 tcp'
# coresendmsg execute flags=string,text node=2 number=1000 command='core-python /home/lk233/core/mytools/nest/temp/transdata.py 10 10.0.0.1 1 udp 2M'

# 10 10.0.0.1 1 tcp 2M 分别代表的含义为：循环次数， 目的IP，业务id， 协议类型， 带宽仅针对udp

