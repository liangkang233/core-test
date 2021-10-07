/*
组播部分：
每个节点都会通过指定网卡向组播域中发送hello包，定时间隔为 'send_interval_time'
通过加入该组播域监听该组播域内消息，做到类似探测网内存活节点数量目的
定时检测时隙(组播域中成员是否有变化),检测时间为 'check_interval_time'
即一次检测时隙周期内接收到对应nemid组播包即认为该节点存活
收发包格式为 "Hello,I'm $nemid"

发送控制网时隙消息：
确定主控制网网桥IP，例如172.16.0.254
接收的组播记录存储至 并发安全set中，我这里的实现采用map(并发不安全)
这是因为我使用select管道传输数据再进行修改map就不会出现竞争冒险，造成并发的读写
各个节点信息综合格式为  I'm 1,recv 2 3 4 5
*/

package main

import (
	"fmt"
	"io"
	"log"
	"net"
	"os"
	"strconv"
	"time"
	// mapset "github.com/deckarep/golang-set"
)

const (
	send_interval_time  = 3
	check_interval_time = 15
	ctrNetport          = 5132
	Multicast_ip        = "224.0.0.250:9981"
)

type myconn struct {
	send   *net.UDPConn
	ctrNet *net.UDPConn
	recv   chan int
}

var (
	Info                     *log.Logger
	Warning                  *log.Logger
	Error                    *log.Logger
	ethname, nemid, ctrNetip string = "", "1", "172.16.0.254"
)

func init() {
	logfile, err := os.OpenFile("Nodes_multicast.log", os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666)
	if err != nil {
		log.Fatalln("打开日志文件失败：", err)
	}
	Info = log.New(logfile, "Info: ", log.Lmicroseconds)
	Warning = log.New(io.MultiWriter(os.Stdout, logfile), "Warning: ", log.Lmicroseconds|log.Lshortfile)
	Error = log.New(io.MultiWriter(os.Stderr, logfile), "Error: ", log.Lmicroseconds|log.Lshortfile)

	// 使用参数1的网卡发送和监听组播包(取出其ip作源地址), 不输入参数使用默认路由
	// 参数2代表运行客户端nem节点号，默认为1
	// 参数3代表主控网ip，默认为172.16.0.254
	if len(os.Args) > 3 {
		ethname = os.Args[1]
		nemid = os.Args[2]
		ctrNetip = os.Args[3]
	} else {
		Warning.Printf("参数错误, 使用默认路由 nemid: %s 主控制网ip: %s\n", nemid, ctrNetip)
	}
}

func main() {
	conn, err := multicast_init(ethname, ctrNetip)
	if err != nil {
		Error.Fatalln("multicast 初始化失败:", err)
	}
	defer conn.send.Close()
	defer conn.ctrNet.Close()
	Info.Println("Nodes successfully initialized: \n\tmulticast send addr", conn.send.LocalAddr().String(),
		"\n\tListenMulticast is", Multicast_ip, "\n\tctrNet addr:", conn.ctrNet.RemoteAddr().String())
	send_interval := time.Tick(time.Second * send_interval_time)
	check_interval := time.Tick(time.Second * check_interval_time)

	myset := make(map[int]int)

	for {
		select {
		//定时发送组播hello包
		case <-send_interval:
			Info.Println("\"send msg\"")
			s := []byte(fmt.Sprintf("Hello,I'm %s", nemid))
			conn.send.Write(s)
		//检查并发送时隙表
		case <-check_interval:
			temp, num := "", 0
			for Multicast_id, nums := range myset {
				if nums == 0 {
					continue
				}
				num++
				myset[Multicast_id] = 0
				temp = temp + " " + strconv.Itoa(Multicast_id)
			}
			// num==0 也发送，会使得时隙全为它分配
			// 考虑大小端问题，int转为string再用byte传 不直接int转byte
			temp = fmt.Sprintf("I'm %s,received %d packets:", nemid, num) + temp
			Info.Println("\"check schedul\"", temp)
			conn.ctrNet.Write([]byte(temp))
		//处理组播hello包信息
		case num := <-conn.recv:
			// Info.Println("\"recv msg\" ", num)
			myset[num]++
		}
	}
}

// 取得网卡的任意一个有效ipv4地址
func gain_ip(ethname string) net.IP {
	eth, _ := net.InterfaceByName(ethname)
	Addrs, err := eth.Addrs()
	if err != nil {
		// Warning.Println(err) //网卡无效
		return nil
	}
	for _, Addr := range Addrs {
		if ipnet, ok := Addr.(*net.IPNet); ok && !ipnet.IP.IsLoopback() { //接口强转为结构体
			if ipnet.IP.To4() != nil {
				return ipnet.IP.To4()
			}
		}
	}
	return nil
}

// 组播及控制网的初始化
func multicast_init(ethname, ctrNetip string) (myconn, error) {
	// 组播发送套接字的初始化
	ethAddr := gain_ip(ethname)
	if ethAddr == nil {
		Warning.Printf("Failed to retrieve valid ipv4 address as source address,\nsearch for matching route to send\n")
		ethAddr = net.IPv4zero
	}
	srcAddr := &net.UDPAddr{IP: ethAddr, Port: 0}
	Multicast_addr, _ := net.ResolveUDPAddr("udp", Multicast_ip)
	send, err := net.DialUDP("udp", srcAddr, Multicast_addr)
	if err != nil {
		return myconn{}, err
	}

	// 组播监听套接字的初始化
	eth, _ := net.InterfaceByName(ethname)
	listener, err := net.ListenMulticastUDP("udp", eth, Multicast_addr)
	if err != nil {
		send.Close()
		return myconn{}, err
	}

	// 控制网套接字的初始化
	srcAddr = &net.UDPAddr{IP: net.IPv4zero, Port: 0}
	dstAddr := &net.UDPAddr{IP: net.ParseIP(ctrNetip), Port: ctrNetport}
	ctrNet, err := net.DialUDP("udp", srcAddr, dstAddr)
	if err != nil {
		send.Close()
		listener.Close()
		return myconn{}, err
	}
	// ctrNet.Write([]byte("hello"))
	// fmt.Printf("<%s>\n", ctrNet.RemoteAddr())

	// go的匿名函数默认捕获上下文变量,开协程捕获组播消息
	data := make([]byte, 1024)
	datach := make(chan int, 0)
	go func() {
		defer listener.Close()
		for {
			n, remoteAddr, err := listener.ReadFromUDP(data)
			if err != nil {
				Warning.Printf("error during read: %s", err)
				continue
			}
			if remoteAddr.IP.Equal(ethAddr) {
				continue // 排除自身发出的组播包
			}
			s := string(data[:n])
			Info.Printf("receive %s %d bytes: %s\n", remoteAddr, n, s)
			_, err = fmt.Sscanf(s, "Hello,I'm %d", &n)
			if err != nil {
				Warning.Printf("error during Sscanf: %s", err)
				continue
			}
			datach <- n
		}
	}()
	return myconn{send: send, recv: datach, ctrNet: ctrNet}, nil
}
