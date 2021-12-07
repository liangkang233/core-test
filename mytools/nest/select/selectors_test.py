# coding: utf-8
import selectors
import socket

# https://www.cnblogs.com/wztshine/p/12091062.html
# 官方文档：https://docs.python.org/3/library/selectors.html

# 根据平台自动选择最佳的IO多路机制，比如linux就会选择epoll,windows会选择select
sel = selectors.DefaultSelector()


def accept(sock, mask):
    # 建立客户端连接
    conn, addr = sock.accept()
    print('accepted', conn, 'from', addr)
    # 设置非阻塞模式
    conn.setblocking(False)
    # 再次注册一个连接，将其加入监测列表中，
    sel.register(conn, selectors.EVENT_READ, read)


def read(conn, mask):
    try:   # 捕获客户端强制关闭的异常（如手动关闭客户端终端）
        data = conn.recv(1000)  # Should be ready
        if data:
            print('echoing', repr(data), 'to', conn)
            conn.send(data)  # Hope it won't block
        else:
            print('Client closed.', conn)
            # 将conn从监测列表删除
            sel.unregister(conn)
            conn.close()
    except ConnectionResetError:
        print('Client forcibly closed.', conn)
        # 将conn从监测列表删除
        sel.unregister(conn)
        conn.close()


# 创建socket对象
sock = socket.socket()

# 绑定端口，设置监听
sock.bind(('localhost', 1234))
sock.listen(100)

# 设置为非阻塞模式
sock.setblocking(False)

# 注册一个文件对象，监测它的IO事件，data是和文件对象相关的数据（此处放置了一个 accept 函数的内存地址）
# register(fileobj, events, data=None)
sel.register(sock, selectors.EVENT_READ, accept)

while True:
    '''
    sel.select()
    看似是select方法，实际上会根据平台自动选择使用select还是epoll
    它返回一个(key, events)元组, key是一个namedtuple类型的元组，可以使用 key.name 获取元组的数据
    key 的内容(fileobj,fd,events,data)：
        fileobj    已经注册的文件对象
        fd         也就是第一个参数的那个文件对象的更底层的文件描述符
        events     等待的IO事件
        data       可选项。可以存一些和fileobj有关的数据，如 sessioin 的 id
    '''
    events = sel.select()     # 监测有无活动对象，没有就阻塞在这里等待
    for key, mask in events:  # 有活动对象了
        callback = key.data     # key.data 是注册时传递的 accept 函数
        callback(key.fileobj, mask)   # key.fileobj 就是传递的 socket 对象
