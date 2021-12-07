#!/home/hyh/.cache/pypoetry/virtualenvs/core-zgg0mQdA-py3.6/bin/python3

import iperf3, socket
import sys
import pymysql
import logging
#主控网ip 端口
HOST = '172.16.0.254'
PORT = 8081
address = (HOST, PORT)

def init_client(id, serverhost, duration, protocol):
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        client = iperf3.Client()
    except:
        print("Error, iperf3 client init failed!")
        exit(1)
    client.duration = duration # Measurement time [sec]
    client.server_hostname = serverhost # Server's IP address
    client.protocol = protocol
    if protocol == "tcp":
        client.bandwidth = 2 * 1024 * 1024
    else :
        client.bandwidth = 512 * 1024

    print('Connecting to {0}:{1}'.format(client.server_hostname, client.port))
    result = client.run()

    if result.error:
        print(result.error)
    else:
        print('')
        print('Test completed:')
        print('Average transmitted data in all sorts of networky formats:')
        if client.protocol == 'tcp':
            print('  retransmits        {0}'.format(result.retransmits))
            print('  Megabits per second  (Mbps)  {0}'.format(result.sent_Mbps))
            #senddata = str(id) + ' ' + str(result.retransmits) + ' ' + str(round(result.sent_Mbps, 3))
            senddata = '{0} {1} {2} {3}'.format(id, result.retransmits, round(result.sent_Mbps, 3), 'tcp')
        elif client.protocol == 'udp':
            print('  lost_percent       {0}'.format(result.lost_percent))
            print('  lost_packets       {0}'.format(result.packets))
            print('  Mbps               {0}'.format(result.Mbps))
            #senddata = str(id) + ' ' + str(result.lost_percent) +' ' + str(round(result.Mbps, 3)) 
            senddata = '{0} {1} {2} {3}'.format(id, round(result.lost_percent, 3), round(result.Mbps, 3), 'udp')   
        print('')
        #将数据发给主控网
        udp_socket.sendto(senddata.encode("utf-8"), address)

if __name__ == "__main__":
    times = int(sys.argv[5])
    for i in range(times):
        init_client(int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4])



