#!/bin/bash
# 安装CRradio模型脚本

if [ `whoami` != "root" ];then
	echo "Please run it as a superuser"
    exit 0
fi

# 替换core.conf
myemanedir="emane_models_dir = $HOME/.core/myeman"
sed -i "s#.*emane_models_dir.*#$myemanedir#" /etc/core/core.conf
# -i替换 -e仅打印 -n 仅打印替换部分 sed中替换分割符可以用/ 或s后的任意字符, 上面使用的替换为#
# 使用/时字符串内的/ ' "要加\转义 即为 \/ \' \"
# 并且可以替换匹配内容中的部分字符串 例如 echo 'key_buffer_size=11M'|sed -r '/key_buffer_size=/ s#11M#123kb#g'

# 创建文件夹 并添加新模型文件
# cp /usr/share/emane/manifest/CRradio.xml ../CRradio_module_files/CRradio.xml
# cp -r /usr/share/emane/xml/models/mac/CRradioscheduler ../CRradio_module_files/
cp ../CRradio_module_files/CRradio.xml /usr/share/emane/manifest/CRradio.xml
cp -r ../CRradio_module_files/CRradioscheduler /usr/share/emane/xml/models/mac/

# 虚拟环境中安装库
cd ~/core/daemon
poetry run pip install psutil


