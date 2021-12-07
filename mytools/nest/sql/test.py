from core import constants, utils
import socket, pymysql

# SQL 插入语句
sql = """INSERT INTO EMPLOYEE(FIRST_NAME,
         LAST_NAME, AGE, SEX, INCOME)
         VALUES ('Mac', 'Mohan', 20, 'M', 2000)"""

# SQL 删除语句
sql = "DELETE FROM EMPLOYEE WHERE AGE > %s" % (20)

# SQL 更新语句
sql = "UPDATE EMPLOYEE SET AGE = AGE + 1 WHERE SEX = '%c'" % ('M')



def mysql_cmd(cursor, db, sql) -> None: #增 改 删
    try:
        # 执行SQL语句
        cursor.execute(sql)
        # 提交修改
        db.commit()
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
ipport = ("172.16.0.254",8081)
# ipport = ("192.168.137.200",8081)
udp_socket.bind(ipport)
# con = pymysql.connect(db='zhongkeyuan', user='root', passwd='123456', host='192.168.0.1', port=3306)
con = pymysql.connect(db='zhongkeyuan', user='root', passwd='123456', host='192.168.137.199', port=3306)
# 使用cursor()方法获取操作游标 
cursor = con.cursor()
mysql_cmd(cursor, con, "DELETE FROM process_lossrate")
for i in range(24):
    sql = f"INSERT INTO process_lossrate(id, tose_num) VALUES({i+1}, 0.0)"
    mysql_cmd(cursor, con, sql)

print('nihao')
# while True:
for i in range(24):
    recv_msg, addr = udp_socket.recvfrom(1024)
    # recv_msg = recv_data[0] # 信息内容
    recv_msg=recv_msg.decode("utf-8")
    print(recv_msg)
    sql = f"UPDATE process_lossrate set tose_num='{recv_msg}' WHERE id = {i+1}"
    # sql = f"UPDATE process_lossrate set tose_num='as' WHERE id = {i+1}"
    mysql_cmd(cursor, con, sql)

con.close()