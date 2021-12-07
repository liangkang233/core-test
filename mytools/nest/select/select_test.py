import select
import socket
import sys
import queue

# https://www.cnblogs.com/wztshine/p/12091062.html

# 生成socket对象
server = socket.socket()
# 设置非阻塞模式
server.setblocking(False)

# 绑定地址，设置监听
server.bind(('localhost',9999))
server.listen(5)

# 将自己也放进待监测列表里
inputs = [server, ]
outputs = []
message_queues = {}

while True:
    '''
    关于socket可读可写的判断，可以参考博客：https://blog.csdn.net/majianfei1023/article/details/45788591
    '''
    rlist, wlist, elist = select.select(inputs,outputs,inputs) #如果没有任何fd就绪,那程序就会一直阻塞在这里

    for r in rlist:  # 遍历已经可以准备读取数据的 fd
        if r is server: # 如果这个 fd 是server，即 server 有数据待接收读取，说明有新的客户端连接过来了
            conn, client_addr = r.accept()
            print("new connection from",client_addr)
            conn.setblocking(False)
            inputs.append(conn) # 将这个新的客户端连接添加到检测的列表中
            message_queues[conn] = queue.Queue() # 用队列存储客户端发送来的数据，等待服务器统一返回数据

        else:          # 这个可读的 r 不是服务器，那就是某个客户端。就是说客户端发送数据过来了，这些数据处于待读取状态
            try:       # 异常处理，这是为了防止客户端异常断开报错（比如手动关掉客户端黑窗口，服务器也会跟着报错退出）
                data = r.recv(1024)
                if data:    # 根据判断data是否为空，判断客户端是否断开
                    print("收到来自[%s]的数据:" % r.getpeername()[0], data)
                    message_queues[r].put(data)   # 收到的数据先放到queue里,一会返回给客户端
                    if r not in outputs:
                        outputs.append(r)     # 放进可写的fd列表中，表明这些 fd 已经准备好去发送数据了。
                else:   # 如果数据为空，表明客户端断开了
                    print('客户端断开了')
                    if r in outputs:
                        outputs.remove(r)    #  清理已断开的连接
                    inputs.remove(r)         # 清理已断开的连接
                    del message_queues[r]    # 清理已断开的连接
            except ConnectionResetError:     # 如果报错，说明客户端断开了
                print("客户端异常断开了", r)
                if r in outputs:
                    outputs.remove(r)   # 清理已断开的连接
                inputs.remove(r)        # 清理已断开的连接
                del message_queues[r]  # 清理已断开的连接

    for w in wlist:       # 遍历可写的 fd 列表，即准备好发送数据的那些fd
        # 判断队列是否为空
        try :
            next_msg = message_queues[w].get_nowait()
        except queue.Empty:
            # print("client [%s]" % w.getpeername()[0], "queue is empty..")
            outputs.remove(w)
        # 队列不为空，就把队列中的数据改成大写，原样发回去
        else:
            # print("sending msg to [%s]"% w.getpeername()[0], next_msg)
            w.send(next_msg.upper())

    for e in elist:   # 处理报错的 fd
        e.close()
        print("Error occured in ",e.getpeername())
        inputs.remove(e)
        if e in outputs:
            outputs.remove(e)
        del message_queues[e]