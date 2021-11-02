import socket
from core import constants, utils

HOST='172.16.0.0'
PORT=50007
#args = 'coresendmsg execute flags=string,text node=1 number=1000 command="iperf3 -s"'
#args = 'coresendmsg execute flags=string,text node=2 number=1000 command="iperf3 -c 10.0.0.1 -u" -l'
#args = 'coresendmsg execute flags=string,text node=' + str(i) + ' number=1000 command="iperf3 -c 10.0.0.' + str(i) + ' -u" -l'
nodenums = 49
nodes = []
for i in range(nodenums):
    nodes.append(i+1)
#奇数号节点监听udp
for i in nodes[2::2]:
    args = "coresendmsg execute flags=string,text node=" + str(i) + " number=1000 command='iperf3 -s'"
    utils.cmd(args)
#偶数号节点执行transdata.py 发送udp
for i in nodes[1::2]:
    ip = '10.0.0.' + str(i)
    #args = "coresendmsg execute node=" + str(i) + " number=1000 command='python3 /home/hyh/core/transdata.py " + ip + "'"
    args = "coresendmsg execute node=" + str(i) + " number=1000 command='/home/lk233/core/mytools/sql/transdata.py'"
    #print(args)
    
    
    
    
    
    #储存结果
    #res1 = utils.cmd(args).split('\n')[-5]
    #print(res1)
    #丢包率
    #packetloss = res1.split()[-1][1:-1:1]
    #print(packetloss)
    #速率
    #dataspeed = res1.split()[6]
    #print(dataspeed)
    #res = res + res1 + '\n'
    
