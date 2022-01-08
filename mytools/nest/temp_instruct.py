#!/home/lk233/.cache/pypoetry/virtualenvs/core-3XChpotV-py3.6/bin/python
# coding: utf-8

"""
模拟前端对后端进行仿真操作，包括(对数据库的写入 发送仿真启动、停止等指令)
"""
import os
import socket
import json
from enum import Enum, unique
from sql import nest_data

Nest_path: str = os.path.dirname(os.path.abspath(__file__))
scenario_path: str = os.path.join(Nest_path, "xmls")

@unique
class Instr(Enum):
    created_session = 1
    start_session = 2
    run_node_cmd = 3
    stop_session = 4
    open_session = 5
    get_sessions = 6

    @classmethod
    def get(cls, name: str) -> "Instr":
        try:
            return Instr(name)
        except ValueError:
            return None


filepath: str = os.path.join(os.path.split(__file__)[0], "temp")
# print(path)


def Created_Session(sock):
    msg = {'instr': Instr.created_session.value}
    msg = json.dumps(msg).encode('utf-8')
    sock.send(msg)  # 发送后堵塞等待后台返回的会话
    recv = json.loads(sock.recv(1024).decode('utf-8'))
    print(f"会话 {recv['session_id']} 创建成功")
    return recv['session_id']


def Start_Session(sock):
    session_id = int(input("指定要配置的会话号:"))
    print("读取对应参数文件 例如XXX/nest/temp/XXX 并导入数据库，不输入即为设定默认值")
    # 读取文件并插入数据库
    # index = input("设置系统参数: config")
    # nest_data.insert(session_id, "config", os.path.join(filepath, f"config{index}"))
    # index = input("设置节点参数: nodes")
    # nest_data.insert(session_id, "nodes",
    #                  os.path.join(filepath, f"nodes{index}"))
    # index = input("设置链路关系: links")
    # nest_data.insert(session_id, "links",
    #                  os.path.join(filepath, f"links{index}"))
    # index = input("设置节点服务文件: services")
    # nest_data.insert(session_id, "services",
    #                  os.path.join(filepath, f"services{index}"))
    # index = input("设置无线参数: emanes")
    # nest_data.insert(session_id, "emanes",
    #                  os.path.join(filepath, f"emanes{index}"))

    msg = {'instr': Instr.start_session.value,
           'session_id': session_id}
    msg = json.dumps(msg).encode('utf-8')
    sock.send(msg)  # 发送后堵塞等待执行结果
    recv = json.loads(sock.recv(1024).decode('utf-8'))
    print(recv)
    return


def Run_Node_Cmd(sock):
    session_id = int(input("指定要配置的会话号:"))
    nodeid = int(input("节点id为:"))
    cmd = input("执行命令")
    wait = input("是否堵塞等待命令返回 1为堵塞等待,否则不等待")
    if wait == "1":
        wait = True
    else:
        wait = False
    msg = {
        'instr': Instr.run_node_cmd.value,
        'session_id': session_id,
        'nodeid': nodeid,
        'cmd': cmd,
        'wait': wait,
    }
    msg = json.dumps(msg).encode('utf-8')
    sock.send(msg)
    recv = json.loads(sock.recv(1024).decode('utf-8'))
    print(recv)
    return


def Stop_Session(sock):
    inp = int(input('停止会话为:'))
    msg = {'instr': Instr.stop_session.value,
           'session_id': inp}
    msg = json.dumps(msg).encode('utf-8')
    sock.send(msg)
    recv = json.loads(sock.recv(1024).decode('utf-8'))
    print(f"{recv}")
    # print(f"会话 {recv['session_id']} 成功停止并清理")
    print("删除对应表 （TODO）")
    return


def Open_Session(sock):
    # 后台运行指定场景
    filepath = input('执行场景为: (场景对应路径为 XXX/nest/xmls/输入值):  ')
    filepath = os.path.join(scenario_path, filepath)
    msg = {'instr': Instr.open_session.value,
           'filepath': filepath,
           }
    msg = json.dumps(msg).encode('utf-8')
    sock.send(msg)
    recv = json.loads(sock.recv(1024).decode('utf-8'))
    print(f"{recv}")
    return


def Get_Sessions(sock):
    msg = {'instr': Instr.get_sessions.value, }
    msg = json.dumps(msg).encode('utf-8')
    sock.send(msg)
    recv = json.loads(sock.recv(10240).decode('utf-8'))
    print(f"{recv}")
    return


Instructions = {
    Instr.created_session: Created_Session,
    Instr.start_session: Start_Session,
    Instr.run_node_cmd: Run_Node_Cmd,
    Instr.stop_session: Stop_Session,
    Instr.open_session: Open_Session,
    Instr.get_sessions: Get_Sessions,
}


def help():
    print(
        f"{Instr.created_session.value} : 创建会话",
        f"\n{Instr.start_session.value} : 设定具体参数并执行仿真",
        f"\n{Instr.run_node_cmd.value} : 执行节点命令",
        f"\n{Instr.stop_session.value} : 停止并删除会话",
        f"\n{Instr.open_session.value} : 后台执行对应场景",
        f"\n{Instr.get_sessions.value} : 获取所有会话状态",
    )


def main(flag=False):
    if(flag):
        sock = socket.socket()
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    SERVER_ADDR = ('localhost', int(nest_data.f["nestport"]))
    sock.connect(SERVER_ADDR)
    help()
    try:
        while True:
            inp = input('请输入指令:')
            if inp == '':
                continue
            callback = Instr.get(int(inp))
            if callback is None:
                print(f"无效指令")
                help()
                continue
            callback = Instructions[callback]
            callback(sock)
    except EOFError:
        pass
    except KeyboardInterrupt:
        pass
    finally:  # 无论是否捕获到except 都会进入finally
        print('\nPower your dreams!')
        sock.close()
        nest_data.sqlcon.close()
        eval


if __name__ == "__main__":
    # main(True)  # tcp测试
    main()  # udp测试
