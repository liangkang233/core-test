# 使用说明:

## 依赖
虚拟环境使用

```bash
cd daemon 
poetry add selectors
poetry add pymysql
```

物理环境直接安装
```
pip3 install selectors
poetry add pymysql
```


## 执行

后端执行：`core-python nest_server.py`

模拟前端：`core-python temp_instruct.py`

## 主要文件介绍：

**nest_server** 和 **temp_instruct** 就是一对接收发送对应json指令的tcp/udp服务器与客户端


**tool文件夹下**
- nest_core 

    是指令解析并实例化场景的关键，其仿真实现原理为调用core-daemon的 grpc api

- mylog 

    定义文件路径变量 日志优先级

- tlv_apimsg

    是对系统 tlv api的通用工具包

**sql文件夹下** 的 nest_data 定义数据库的连接实例，解析及插入

**temp文件夹** 存储文件为模拟前端对**场景节点链路等的定义**文件，模拟前端执行时依照对应会话号读取这些文件并插入数据库

**xmls文件夹** 存储运行的会话场景备份
