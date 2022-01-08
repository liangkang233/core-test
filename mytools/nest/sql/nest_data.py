from typing import List
from tool.mylog import logger, nest_config
import pymysql
from pymysql.cursors import DictCursor
import datetime

""" 
删除表
    DROP TABLE 表名
清空表内容，并将自增id设置为1
    DELETE FROM location_test
    ALTER TABLE location_test AUTO_INCREMENT=1

like仅复制结构
注意！ 创建TEMPORARY临时表只对当前连接有效 navicat 或其他用户无法查看 
    mysqltest('CREATE TABLE IF NOT EXISTS session_2_nodes LIKE session_1_nodes')
    mysqltest('CREATE TEMPORARY TABLE IF NOT EXISTS session_2_nodes (LIKE session_1_nodes)')
复制表结构及数据到新表
    CREATE TABLE 新表 SELETE * FROM 旧表 
所以真正的表结构复制方法是LIKE方法，如果不需要考虑表原本的属性包括存储引擎、备注、主键、索引等那么select复制方法是个不错的方法并且还能连同数据一起复制。
    INSERT INTO session_1_nodes(xyz, types, servers_set, servers_config) values('1 2 3','ospf-mdr', 'ipforword', 'echo hello')

SQL 插入语句
    "INSERT INTO 表名(FIRST_NAME, \
    LAST_NAME, AGE, SEX, INCOME) \
    VALUES ('Mac', 'Mohan', 20, 'M', 2000)"

SQL 删除语句
    "DELETE FROM 表名 WHERE AGE > %s" % (20)

SQL 更新语句
    "UPDATE 表名 SET AGE = AGE + 1 WHERE SEX = '%c'" % ('M')

SQL 存在更新，不存在插入(后面的部分是插入的值，前面是更新值)
    "INSERT INTO 表名(唯一索引列, 列2, 列3) VALUE(值1, 值2, 值3) ON DUPLICATE KEY UPDATE 列=值, 列=值"
    效果同上，不过其更新流程是 删除后插入
    "REPLACE INTO 表名(num, name, mobile) VALUES(3000, '小山', '14412341234')"
"""

# 连接数据库
with open(nest_config, "r") as f: 
    f=f.read().splitlines() #获取 文件全部数据 不要回车, 返回结果是一个列表
f = {temp.split()[0]:temp.split()[2] for temp in f}
sqlcon = pymysql.connect(db=f["db"], user=f["user"],
                         passwd=f["passwd"], host=f["host"], port=int(f["port"]))
cursor = sqlcon.cursor()


def mysql_cmd(sql) -> None:
    """
    操作: 增、改、删
    :sql: sql为mysql语句
    """
    try:
        cursor.execute(sql)
        # 提交修改
        sqlcon.commit()
        return True
    except pymysql.Error as e:
        # 发生错误时回滚
        logger.error(f"write error {e}")
        sqlcon.rollback()
        return False


def mysql_cmd1(sql, flag=False) -> tuple:
    """
    操作: 查
    :sql: sql为mysql语句
    :flag: flag默认False, 为true 返回查询值为字典类型
    """
    try:
        cursor1 = cursor
        if flag:
            cursor1 = sqlcon.cursor(DictCursor)
        cursor1.execute(sql)
        results = cursor1.fetchall()
        return results
    except pymysql.Error as e:
        # 发生错误时回滚
        logger.error(f"read error {e}")


def mysql_cmd2(sql, args) -> None:
    """
    批量操作
    :sql: sql为mysql语句,包含转移符例如%s %d
    :args: 传入批量执行的数据元祖列表,对应转移符号参数
    """
    try:
        # 执行SQL语句
        cursor.executemany(sql, args)
        # 提交修改
        sqlcon.commit()
        return True
    except pymysql.Error as e:
        # 发生错误时回滚
        logger.error(f"executemany error {e}")
        sqlcon.rollback()
        return False


def Abtain_Satellite_Position(file_path, period):
    """
    批量插入星座经纬高测试
    """
    sql = "INSERT INTO location_test(longitude, latitude, altitude) values(%s,%s,%s)"
    len, args = 0, []
    with open({file_path}, 'r', encoding='utf-8') as locations:
        print(datetime.datetime.now())
        for location in locations:
            len += 1
            data = location.split()
            args.append((data[6], data[7], data[8]))
            if len == period:
                mysql_cmd("DELETE FROM location_test")
                mysql_cmd("ALTER TABLE location_test AUTO_INCREMENT=1")
                mysql_cmd2(sql, args)
                len = 0
                args = []
        print(datetime.datetime.now())
    sqlcon.close()


""" 
def Nodes_Mobility(session_id):
    # 场景初始化时执行此函数修改高度，之后循环遍历修改geo
    core = CoreGrpcClient()
    core.connect()
    while True:
        mysql_cmd('LOCK TABLES satellite_LLA_test READ')
        sql = f'SELECT * FROM satellite_LLA_test'
        positions = mysql_cmd1(sql, True)
        mysql_cmd('UNLOCK TABLES')
        if not positions:
            continue
        for position in positions:
            nodeid = position['node_id']
            lat = position['latitude']
            lon = position['longitude']
            alt = position['altitude']
            geo = Geo(lon=lon, lat=lat, alt=alt)
            logger.debug(f"nodeid, {geo}")
            try:
                response = core.edit_node(session_id, nodeid, geo=geo)
            except:
                # logger.error('set postion fault')
                continue
        time.sleep(1) """


def insert(session_id, type, file_path) -> bool:
    """
    根据会话号创建或清空对应表，根据文本批量插入数据至该表
    数据文件第一行对应表结构，之后每一行对应一组数据以,分割 (不填入数据即为null)
    返回是否全部插入成功的bool
    """
    instr = "REPLACE"
    table = "session_all_config"
    if type != "config":  # 非config表需要新建或清空原数据
        instr = "INSERT"
        table = f"session_{session_id}_{type}"
        mysql_cmd(f"CREATE TABLE IF NOT EXISTS {table} LIKE session_template_{type}")
        mysql_cmd(f"DELETE FROM {table}")
    # mysql_cmd(f"ALTER TABLE session_{session_id}_{type} AUTO_INCREMENT=1")
    try:
        with open(f'{file_path}', 'r', encoding='utf-8') as datas:
            t_sql = datas.readline()[:-1].split(',')  # -1是为了去掉回车之后splite取出数据格式
            for data in datas.read().splitlines():
                i, sql, format = -1, '', ''
                # print(data.split(','))
                if type == "config": #config类型自动补齐会话号
                    sql, format = "session_id,", f"{session_id},"
                for d in data.split(','):
                    i += 1
                    if (d == ''):
                        continue
                    sql = sql + f"{t_sql[i]},"
                    format = format + f"{d},"
                sql = f"{instr} INTO {table} (" + \
                    sql[:-1] + ") values(" + format[:-1] + ")"
                # print(sql)
                if not mysql_cmd(sql):
                    return False
    except FileNotFoundError:
        print(f"{file_path}不存在，使用默认参数")
    return True


def set_status(session_id, status):
    """
    根据会话号设定会话状态
    """
    state = {
        1:"DEFINITION",
        2:"CONFIGURATION",
        3:"INSTANTIATION",
        4:"RUNTIME",
        5:"DATACOLLECT",
        6:"SHUTDOWN",
    }
    status = state[status]
    sql = f"UPDATE session_all_config SET status = '{status}' WHERE session_id = {session_id}"
    mysql_cmd(sql)


def parse(session_id) -> List:
    """
    根据会话号解析对应数据库，并导出数据字典列表
    """
    sql = f'SELECT * FROM session_{session_id}_nodes'
    nodes = mysql_cmd1(sql, True)
    sql = f'SELECT * FROM session_{session_id}_links'
    links = mysql_cmd1(sql, True)
    sql = f'SELECT * FROM session_{session_id}_services'
    services = mysql_cmd1(sql, True)
    sql = f'SELECT * FROM session_{session_id}_emanes'
    emane = mysql_cmd1(sql, True)
    sql = f'SELECT * FROM session_all_config WHERE session_id = {session_id}'
    session_config = mysql_cmd1(sql, True)

    logger.debug(nodes, links, services, emane, session_config)
    # return (nodes, links, services)
    return (nodes, links, services, emane, session_config)

def delete(session_id):
    """
    删除对应数据库内容
    """
    sql = f'DROP TABLE session_{session_id}_nodes'
    mysql_cmd(sql)
    sql = f'DROP TABLE session_{session_id}_links'
    mysql_cmd(sql)
    sql = f'DROP TABLE session_{session_id}_services'
    mysql_cmd(sql)
    sql = f'DROP TABLE session_{session_id}_emanes'
    mysql_cmd(sql)
    sql = f'DELETE FROM session_all_config WHERE session_id = {session_id}'
    mysql_cmd(sql)

def mysqltest(sql):
    """
    普通sql语句测试
    """
    con = pymysql.connect(db='zhongkeyuan', user='user',
                          passwd='123456', host='10.16.32.5', port=3306)
    cursor = con.cursor()
    sql = ''
    mysql_cmd(cursor, con, sql)
    input('nihao')
    con.close()


if __name__ == '__main__':
    # Abtain_Satellite_Position(1584)
    # insert(2, "/home/lk233/core/mytools/nest/sql/nodes.txt")
    insert(1, "nodes", "nodes1")
    parse(1)
