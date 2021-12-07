# required imports
# coding: utf-8

from core.api.grpc import client
import grpc




# create grpc client and connect
core = client.CoreGrpcClient()
core.connect()

session_id = 1

try:
    nodeid = int(input("节点id为:"))
    ins = input("执行命令")
    response = core.node_command(session_id, nodeid, ins)
    print(response.output, response.return_code, sep='\n')
    ins = input("执行等待返回命令")
    # 即为执行 vcmd -c /tmp/pycore.1/N1 -- ls
    response = core.node_command(session_id, nodeid, ins, wait=True)
    print(response.output, response.return_code, sep='\n')
    input("获取节点终端cmd执行命令")
    response = core.get_node_terminal(session_id, 1)
    print(response.terminal)
    # 例如 vcmd -c /tmp/pycore.1/N1 -- /bin/bash

except grpc.RpcError as e:
    print(e)
    core.close()

# input("stop")
# core.stop_session(session_id)
# core.delete_session(session_id)