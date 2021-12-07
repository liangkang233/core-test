#!/home/lk233/.cache/pypoetry/virtualenvs/core-3XChpotV-py3.6/bin/python

import socket, sys
from core import constants, utils
#主控网ip 端口
HOST = '172.16.0.254'
PORT = 7979
address = (HOST, PORT)

def main():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    for i in range(int(sys.argv[1])):
        ip = sys.argv[2]
        # command = "iperf3 -c " + ip + " -u -t 1s -M 1024"
        command = "iperf3 -c " + ip + " -t 1s -M 1024"
        print(command)
        res1 = utils.cmd(command).split('\n')[-4]
        split = res1.split()

        data = []
        data.append(sys.argv[3])  #业务id
        # data.append(split[-1][1:-2:1])#丢包率
        data.append(split[8])#丢包率
        data.append(split[6])   #流量
        # data.append(split[-4])  #抖动时延
        
        print(data)
        send_data = ' '.join(data)
        
        udp_socket.sendto(send_data.encode("utf-8"), address)

if __name__ == '__main__':
    main()