#!/usr/bin/env python3
import socket
import json


def main():
    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # msg1 = [{'src':"zj", 'dst':"zjdst"}]
    msg1 = [{'timestamp': "1", 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
             'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"},
            {'timestamp': "1", 'id': "2", 'name': "3", 'startNodeName': "4", 'startNode': "5",
             'endNodeName': "6", 'businessType': "7", 'frameLength': "8", 'lastedTime': "9", 'spacedTime': "10"}]
    send_data = json.dumps(msg1)
    udp_socket.sendto(send_data.encode('utf-8'),
                      ("127.0.0.1", 8082))  # 8082 app
    udp_socket.close()


if __name__ == '__main__':
    main()
