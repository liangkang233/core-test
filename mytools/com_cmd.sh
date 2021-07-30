#! /bin/bash

#gpsd daemon
emaneeventd eventdaemon.xml -r -d -l 3 -f emaneeventd.log
gpsd -G -n -b $(cat gps.pty)

#gpsd client
cgps

#emaneevent dump
emaneevent-dump -i ctrl0

#emane event serveice, loglevel -- INFO(3)
emaneeventservice eventservice.xml -l 3
#Run with realtime priority and SCHED_RR.  Must  have  superuser privileged.
sudo emaneeventservice eventservice.xml -l 3 -r


#core Scenario file
code ~/.coregui/xmls/
code ~/.core/configs/
#core source Scenario file
code ~/core/gui/data/xmls/
code ~/core/gui/configs/

#core config file
code /etc/core
#core source config file
code ~/core/daemon/data/