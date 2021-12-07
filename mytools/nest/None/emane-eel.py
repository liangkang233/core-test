#!/usr/bin/env python
from emane.events import EventService
from emane.events import LocationEvent
#
# create the event service
# service = EventService(('224.1.2.8',45703,'eth0')) # 容器内发送
service = EventService(('224.1.2.8',45703,'ctrl0.c8')) # 主机发送控制网
#
# create an event setting 10's position
event = LocationEvent()
event.append(2,latitude=40.031290,longitude=-74.523095,altitude=3.000000)
#
# publish the event
service.publish(2,event)
