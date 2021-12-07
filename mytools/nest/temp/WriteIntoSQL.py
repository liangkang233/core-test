#from core import constants, utils
import socket, pymysql


def mysql_cmd(cursor, db, sql) -> None: #增 改 删
    try:
        # 执行SQL语句
        cursor.execute(sql)
        # 提交修改
        # db.commit()
    except pymysql.Error as e:
        # 发生错误时回滚
        print(f"write error {e}")
        db.rollback()
    
def mysql_cmd1(cursor, sql) -> tuple: #查
    try:
        # 执行SQL语句
        cursor.execute(sql)
        results = cursor.fetchall()
        return results
    except pymysql.Error as e:
        # 发生错误时回滚
        print(f"read error {e}")

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ipport = ("0.0.0.0",8081)

udp_socket.bind(ipport)
con = pymysql.connect(db='zhongkeyuan', user='user',
                passwd='123456', host='10.16.31.100', port=3306)
# 使用cursor()方法获取操作游标 
cursor = con.cursor()
# sql = f"INSERT INTO process_lossrate(id, retransmits, lossrate, bandwidth) VALUES({1}, {-1}, {-1.0}, {0})"

mysql_cmd(cursor, con, "DELETE FROM process_lossrate")
con.commit()
for i in range(24):
    sql = f"INSERT INTO process_lossrate(id, retransmits, lossrate, bandwidth) VALUES({i+1}, {-1}, {-1.0}, {0})"
    mysql_cmd(cursor, con, sql)
    con.commit()

print('nihao')

#for i in range(24):
while(1):
    recv_msg, addr = udp_socket.recvfrom(1024)
    # recv_msg = recv_data[0] # 信息内容
    recv_msg=recv_msg.decode("utf-8")
    print(recv_msg)
    recv_info = recv_msg.split()
    protocol = recv_info[-1]
    id = recv_info[0]
    bandwidth = recv_info[2]
    if protocol == 'tcp':
        retransmits = recv_info[1]
        sql = f"UPDATE process_lossrate set retransmits={retransmits}, bandwidth={bandwidth} WHERE id = {id}"
    elif protocol == 'udp':
        lossrate = recv_info[1]
        sql = f"UPDATE process_lossrate set lossrate={lossrate}, bandwidth={bandwidth} WHERE id = {id}"
    mysql_cmd(cursor, con, sql)
    con.commit()
con.close()