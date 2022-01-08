#!/home/lk233/.cache/pypoetry/virtualenvs/core-3XChpotV-py3.6/bin/python
# coding: utf-8

"""
启动套接字 tcp udp皆可，对应该主机的 5132 端口
连接前端, 设定nest分布式仿真服务
后台一直循环等待指令  暂定4种：
    
    :指令1：创建会话，返回会话值
    :指令2: 进行仿真（为防止仿真ssh饱和，还是单线程执行仿真初始化吧）
            仿真初始化完成，返回前端仿真成功数据
    :指令3: 执行对应命令调用api
    :指令4：结束并清理会话

指令统一使用json封装，具体细节参照 nest_core
"""

import json
import socket
import selectors
from sql import nest_data
from tool.nest_core import resolve, core, AllTimer
from tool.mylog import logger


def accept(sel, sock):
    # 建立Tcp客户端连接
    conn, addr = sock.accept()
    logger.info(f'accepted conn from {addr}')
    conn.setblocking(False)
    sel.register(conn, selectors.EVENT_READ, read_T)


def read_T(sel, conn):  # tcp接收数据
    try:
        msg = conn.recv(10240).decode('utf-8')
        src = conn.getpeername()
        if msg:
            msg = json.loads(msg)
            logger.debug(f'recv tcp msg: {msg} from {src}')
            msg = resolve(msg)
            if msg != None:
                msg = json.dumps(msg).encode('utf-8')
                conn.send(msg)
        else:
            logger.debug(f'Client {src} closed.')
            sel.unregister(conn)  # 将conn从监测列表删除
            conn.close()
    except json.decoder.JSONDecodeError as e:
        logger.error(f'invaild json msg: {msg}\n{e}')
        return
    except ConnectionResetError:
        logger.warning(f'Client {src} forcibly closed.')
        sel.unregister(conn)
        conn.close()


def read(sel, conn):  # udp接收数据
    try:
        msg, src = conn.recvfrom(10240)
        if msg:
            msg = json.loads(msg.decode('utf-8'))
            logger.info(f'recv udp msg: {msg} from {src}')
            msg = resolve(msg)
            if msg != None:
                msg = json.dumps(msg).encode('utf-8')
                conn.sendto(msg, src)
    except json.decoder.JSONDecodeError as e:
        logger.error(f'invaild json msg:{msg}\n{e}')
        return


def main():
    # 初始化前后端通信udp与tcp套接字
    SERVER_ADDR = ("0.0.0.0", int(nest_data.f["nestport"]))
    app = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    app.bind(SERVER_ADDR)
    app_T = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    app_T.bind(SERVER_ADDR)
    app_T.listen(100)

    # 设置为非阻塞模式
    app.setblocking(False)
    app_T.setblocking(False)

    # 根据平台自动选择最佳的IO多路机制，例如linux就会选择epoll,windows会选择select
    sel = selectors.DefaultSelector()

    # 注册一个文件对象，监测它的IO事件，data是和文件对象相关的数据（此处放置了一个 accept 函数的内存地址）
    # register(fileobj, events, data=None)
    sel.register(app, selectors.EVENT_READ, read)
    sel.register(app_T, selectors.EVENT_READ, accept)

    try:
        while True:
            mysel = sel.select()        # 监测有无活动对象，没有就阻塞在这里等待
            # key 的内容(fileobj,fd,events,data) : 已经注册的文件对象、文件描述符、等待的IO事件、其他自定义数据
            for key, _ in mysel:
                callback = key.data
                callback(sel, key.fileobj)
    except KeyboardInterrupt:
        pass
    finally: # 无论是否捕获到except 都会进入finally
        app.close()
        app_T.close()
        core.close()
        nest_data.sqlcon.close()
        for T in AllTimer: # 清空定时器
            AllTimer[T].cancel()
        print('\nPower your dreams!')


if __name__ == "__main__":
    main()
    # logger.info('test')
    # nest_data.parse(1)

    # nest_data.insert(1, "config", '/home/lk233/core/mytools/nest/temp/config1')
    # ids = nest_data.parse(1)
    # Emanemodel = (
    #     "emane_rfpipe",
    #     "emane_ieee80211abg",
    #     "emane_tdma",
    # )
    # for sql_node in ids:
    #     print("LKtest", sql_node['emane'])
    #     if not sql_node['emane'] is None:
    #         print(sql_node['emane'] )
    #         emane_mod = Emanemodel[sql_node['emane']]
    #         print(emane_mod)