#from core import constants, utils
import socket, pymysql
import json,datetime
from pymysql.cursors import DictCursor
# from typing import Protocol


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
    
def mysql_cmd1(sql, flag=False) -> tuple:
    """
    操作: 查
    :sql: sql为mysql语句
    :flag: flag默认False, 为true传回字典类型
    """
    try:
        cursor1 = cursor
        if flag:
            cursor1 = con.cursor(DictCursor)
        cursor1.execute(sql)
        results = cursor1.fetchall()
        return results
    except pymysql.Error as e:
        # 发生错误时回滚
        # logger.error(f"read error {e}")
        exit()

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ipport = ("0.0.0.0",5678)

udp_socket.bind(ipport)
con = pymysql.connect(db='zhongkeyuan', user='user',
                passwd='123456', host='10.16.97.148', port=3306)
cursor = con.cursor()
# sql = f"SELECT CONCAT('TRUNCATE TABLE ', TABLE_NAME, ';') FROM information_schema.tables WHERE TABLE_NAME LIKE 'process_%'"

data_statistics = ['delayjitter','enddelay','gencetime','lossrate','outandrece','receive','sendingrate','timingthroughput','transmit','utilratio']
for table in data_statistics:
    sql = f"DELETE FROM process_{table}"
    mysql_cmd(cursor, con, sql)
con.commit()
print('nihao')

while(1):
    simulation_time = str(datetime.datetime.now())

    json_msg, addr = udp_socket.recvfrom(1024)
    json_msg = json_msg.decode("utf-8")
    recv_msg = json.loads(json_msg)

    flow_id = recv_msg.get('flow_id')
    delayjitter = recv_msg.get('delayjitter')
    lossrate = recv_msg.get('lossrate')
    sendingrate = recv_msg.get('sendingrate')
    enddelay = recv_msg.get('delay')
    # 发送数据量
    dr_num = recv_msg.get('transmits')
    # 接受数据量
    value = f'{int(dr_num.split()[0]) * (1 - float(lossrate[0]))} {dr_num.split()[1]}'

    if delayjitter:
        sql = f"INSERT INTO process_delayjitter(id,flow_id,delayjitter) VALUES({flow_id},{flow_id},'{delayjitter}') ON DUPLICATE KEY UPDATE delayjitter='{delayjitter}'"
        mysql_cmd(cursor, con, sql)
    if lossrate:       
        sql = f"INSERT INTO process_lossrate(id,flow_id,lossrate) VALUES({flow_id},{flow_id},'{lossrate}') ON DUPLICATE KEY UPDATE lossrate='{lossrate}'"
        mysql_cmd(cursor, con, sql)
        if dr_num:
            sql = f"INSERT INTO process_timingthroughput(id,sid,simulation_time,throughput) VALUES({flow_id},{flow_id},'{simulation_time}','{dr_num}') ON DUPLICATE KEY UPDATE simulation_time='{simulation_time}',throughput='{dr_num}'"
            mysql_cmd(cursor, con, sql)
            sql = f"INSERT INTO process_outandrece(id,sid,flow_id,dr_num,value) VALUES({flow_id},{flow_id},{flow_id},'{dr_num}','{value}') ON DUPLICATE KEY UPDATE dr_num='{dr_num}',value='{value}'"
            mysql_cmd(cursor, con, sql)
    if sendingrate:
        sql = f"INSERT INTO process_sendingrate(id,sid,simulation_time,sendingrate) VALUES({flow_id},{flow_id},'{simulation_time}','{sendingrate}') ON DUPLICATE KEY UPDATE simulation_time='{simulation_time}',sendingrate='{sendingrate}'"
        mysql_cmd(cursor, con, sql)
    if enddelay:
        sql = f"INSERT INTO process_enddelay(id,flow_id,end_end_delay) VALUES({flow_id},{flow_id},'{enddelay}') ON DUPLICATE KEY UPDATE end_end_delay='{enddelay}'"
        mysql_cmd(cursor, con, sql)
    
    print(flow_id,enddelay,value)
    con.commit()

  
        
       