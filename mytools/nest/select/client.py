from math import e
import socket
import json
from time import sleep
from tkinter.constants import E

from invoke import executor

sock=socket.socket()
sock.connect(('localhost',5132))
# sock.connect(('localhost',1234))
# sock.connect(('localhost',9999))
while True:
    inp = ''
    try:
        while inp == '':
            inp=input('>>>>')
    except EOFError as e:
        print (e)
        sock.close()
        exit()
    # sock.send(inp.encode('utf8'))
    msg1 = [{'timestamp': "1", 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
             'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"},
            {'timestamp': "1", 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
             'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"}]
    send_data = json.dumps(msg1)
    sock.send(send_data.encode('utf8'))
    data=sock.recv(1024)
    print(data.decode('utf8'))
# sock.close()



while True:
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # 从键盘获取数据
    send_data = ''
    try:
        while send_data == '':
            send_data=input('>>>>')
    except EOFError as e:
        print (e)
        udp_socket.close()
        exit()
    # 退出函数
    if send_data == "exit":
        break
    # 可以使用套接字收发数据,此时未绑定发送的端口号，系统每次会随机分配一个
    # udp_socket.sendto("hahaha",对方的IP和port)
    # udp_socket.sendto(b"lalala123",("172.17.3.97",8080))
    udp_socket.sendto(send_data.encode("utf-8"),
                        ("127.0.0.1", 5132))  # 8081 start
    data, _ = udp_socket.recvfrom(1024)
    print(data.decode('utf8'))
    udp_socket.close()
