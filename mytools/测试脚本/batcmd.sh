#!/bin/bash
# 使用coresendmsg控制多个节点执行命令简单脚本
# for i in $(seq 1 $1)
# do
#   模板
#   coresendmsg execute node=$i number=1001 command="$2" # 直接执行
#   coresendmsg execute flags=string,text node=$i number=1001 command="$2" -l #有监听返回值
# done


if [ $# -lt "1" ] ; then
    echo 参数错误
    exit 0
fi
if [[ $2 == "O" ]] || [[ $2 == "o" ]] ; then #此处必须使用[[]]
    for i in $(seq 1 $1) #从节点1-$1 b包含$1
    do
        coresendmsg execute node=$i number=1001 command="/home/lk233/gopl.io/Nodes_multicast eth0 $i \"172.16.0.254\""
    done
        /home/lk233/gopl.io/Schedule_update 172.16.0.254 /home/lk233/.core/configs/configuration/schedule-mytest.xml 1>/dev/null &
    echo 多播启动
else
    for i in $(seq 1 $1)
    do
        coresendmsg execute node=$i number=1001 command="killall Nodes_multicast"
        # coresendmsg execute flags=string,text node=$i number=1001 command="rm -f Nodes_multicast.log"
    done
    killall Schedule_update
    # rm $HOME/Schedule_update.log
    echo 多播关闭
fi