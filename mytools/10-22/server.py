#!/usr/local/bin/core-python
from core import utils
import socket
import pymysql
import json


def mysql_cmd(cursor, db, sql) -> None:  # 增 改 删
    try:
        # 执行SQL语句
        res = cursor.execute(sql)
        # 提交修改
        db.commit()
        return res
    except pymysql.Error as e:
        # 发生错误时回滚
        print(f"write error {e}")
        db.rollback()


def mysql_cmd1(cursor, sql) -> tuple:  # 查
    try:
        # 执行SQL语句
        cursor.execute(sql)
        results = cursor.fetchall()
        return results
    except pymysql.Error as e:
        # 发生错误时回滚
        print(f"read error {e}")


def getcmd(src, dst, num, id):
    args = "coresendmsg execute flags=string,text node=" + \
        dst + " number=1000 command='iperf3 -s'"
    print(args)
    utils.cmd(args)
    ip = '10.0.0.' + str(int(dst)-1)
    args = "coresendmsg execute node=" + src + \
        f" number=1000 command='/home/lk233/core/mytools/sql/transdata.py {num} {ip} {id}'"
    print(args)
    utils.cmd(args)


def main():
    con = pymysql.connect(db='zhongkeyuan', user='root',
                          passwd='123456', host='192.168.137.199', port=3306)
    # 使用cursor()方法获取操作游标
    cursor = con.cursor()
    mysql_cmd(cursor, con, "DELETE FROM process_lossrate")
    print("sql init succeed")
    # for i in range(24):
    #     # sql = f"INSERT INTO process_lossrate(id, tose_num) VALUES({i+1}, 0.0)"
    #     mysql_cmd(cursor, con, sql)

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # localaddr = ("192.168.137.200",8081)
    localaddr = ("0.0.0.0", 8081)
    udp_socket.bind(localaddr)

    recv_data = udp_socket.recvfrom(1024)
    recv_msg = recv_data[0].decode('utf-8').split(',')  # 信息内容
    print(recv_msg)
    arg = f"/bin/bash /home/lk233/generate.sh 1 {recv_msg[0]}"
    # arg=f"/bin/bash /home/lk233/generate.sh {recv_msg[1]} {recv_msg[0]}"
    print(utils.cmd(arg))
    args = "core-gui -b  /home/lk233/rfpipe.imn"
    utils.cmd(args)
    print("complete")
    udp_socket.close()

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # localaddr = ("192.168.137.200",8082)
    localaddr = ("0.0.0.0", 8082)
    udp_socket.bind(localaddr)
    recv_data = udp_socket.recvfrom(10240)[0].decode('utf-8')
    recv_data = json.loads(recv_data)
    udp_socket.close()

    app = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ipport = ("172.16.0.254", 7979)
    # ipport = ("0.0.0.0",7979)
    app.bind(ipport)
    print('app start')
    for data in recv_data:
        # getcmd(data['srcid'], data['dstid'], data['spacedTime'], data['id'])
        getcmd(data['srcid'], data['dstid'], 9000, data['id'])
    # for i in range(24):
    while(True):
        recv_msg, addr = app.recvfrom(1024)
        # recv_msg = recv_data[0]
        recv_msg = recv_msg.decode("utf-8").split()
        print(recv_msg)
        # sql = f"UPDATE process_lossrate set tose_num='{recv_msg}' WHERE id = {i+1}"
        sql = f"SELECT * FROM process_lossrate WHERE id = {recv_msg[0]}"
        if mysql_cmd1(cursor, sql) == ():
            sql = f"INSERT INTO process_lossrate(id, tose_num, traffic, jitter) VALUES({recv_msg[0]}, {recv_msg[1]}, {recv_msg[1]}, {recv_msg[2]})"
        else:
            sql = f"UPDATE process_lossrate set tose_num={recv_msg[1]}, traffic={recv_msg[2]}, jitter={recv_msg[2]} WHERE id = {recv_msg[0]}"
        mysql_cmd(cursor, con, sql)

    con.close()
    app.close()


if __name__ == "__main__":
    main()


# args="sh /home/lk233/1.sh "
# print (utils.cmd(args))
