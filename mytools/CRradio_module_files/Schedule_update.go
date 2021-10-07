/*
首先打开当前场景的时隙分配xml文件，获取基本参数信息
然后定时检测各个节点发送的节点监测消息，根据优先级固定的顺序分配时隙
一定是先排列完全部节点后再继续按照节点优先级顺序排列时隙，
所以优先级高的节点其分配到时隙的可能性越大
当前优先级 简单的处理为 nemid，id越小 优先级越高,具体参考myschedule_create的实现
检测时间间隔与多播程序的时间间隔相同 'check_interval'

注意：这里仅仅是为了处理方便将所有节点时隙数据整合在一起
其实实际各个节点的时隙是单独分派的，例如若两节点n1 n15分别在两个网内（组播域中未互相探测到）
所以他们的时隙很可能是会有重合冲突的部分，但由于组播无法互相探测到可认为是无影响的。
*/

package main

import (
	"bufio"
	"fmt"
	"io"
	"io/ioutil"
	"log"
	"net"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

const (
	check_interval_time = 15
	ctrNetport          = 5132
)

type recvdata struct {
	id     int
	recvid []string
}

type filedata struct {
	slot  int            //时隙个数
	basic []string       //基本字符串
	slots map[int]string //各节点对应的时隙字符串 eg. slots[11] = "10,26"
}

var (
	Info    *log.Logger
	Warning *log.Logger
	Error   *log.Logger
)

func init() {
	if len(os.Args) < 3 {
		log.Fatalln("无效参数，形参1为主控网网卡，形参2为要读取的时隙初始化表文件")
	}
	home := os.Getenv("HOME")
	logfile, err := os.OpenFile(home+"/core/Schedule_update.log", os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0666)
	if err != nil {
		log.Fatalln("打开日志文件失败：", err)
	}
	Info = log.New(logfile, "Info: ", log.Lmicroseconds)
	Warning = log.New(io.MultiWriter(os.Stdout, logfile), "Warning: ", log.Lmicroseconds|log.Lshortfile)
	Error = log.New(io.MultiWriter(os.Stderr, logfile), "Error: ", log.Lmicroseconds|log.Lshortfile)
}

func main() {
	// 解析初始化时隙配置文件
	schedule, err := schedule_Parse(os.Args[2])
	if err != nil {
		Error.Fatalln("解析时隙配置文件失败：", err)
	}

	// 开启监听主控网协程
	recv_ch := make(chan recvdata, 0)
	go recvdatas(recv_ch)
	upfile := os.Args[2][:len(os.Args[2])-4] + "_update.xml"

	check_interval := time.Tick(time.Second * check_interval_time)
	nodes_solt := "" // 类似 <slot index='2,18' nodes='3'> 字符串的总集合
	for {
		select {
		case <-check_interval:
			// 定时将newdata翻译成固定格式,写入并发布时隙表
			if nodes_solt == "" {
				Info.Println("全部节点时隙未变化，取消更新总时隙表文件操作")
				continue
			}
			schedule.basic[3] = nodes_solt[:len(nodes_solt)-1] //去掉多余分号
			if err := write_schedule(upfile, schedule.basic); err != nil {
				Warning.Println("写入时隙表文件失败", err)
			}
			if res := exec_schedule(upfile); res != "" {
				Error.Println(err)
				continue
			}
			Info.Printf("更新时隙文件成功: \"%s\"", upfile)
			nodes_solt = ""
		case datas := <-recv_ch:
			// 接收数据并处理生成的时隙表,填充为newdata
			old, have := schedule.slots[datas.id]
			if !have {
				Warning.Printf("时隙文件未初始化该%d节点，放弃更新该结点", datas.id)
			}
			newdata := myschedule_create(schedule.slot, datas)
			if old == newdata {
				// Info.Printf("%d节点时隙未变化，不更新该节点时隙表", datas.id)
				continue
			}
			Info.Printf("%d节点时隙变化", datas.id)
			schedule.slots[datas.id] = newdata //更新文件中时隙
			nodes_solt += fmt.Sprintf("      <slot index='%s' nodes='%d'>\n      </slot>\n",
				newdata, datas.id)
		}
	}
}

func recvdatas(recv_ch chan recvdata) {
	ethAddr := gain_ip(os.Args[1])
	if ethAddr == nil {
		Error.Fatalln(os.Args[1], "is invalid")
	}
	ctrlNet, err := net.ListenUDP("udp", &net.UDPAddr{IP: ethAddr, Port: ctrNetport})
	if err != nil {
		Error.Fatalln(err)
	}
	defer ctrlNet.Close()
	Info.Printf("主控网监听 <%s> 时隙消息\n", ctrlNet.LocalAddr().String())
	for {
		data := make([]byte, 1024)
		for {
			n, remoteAddr, err := ctrlNet.ReadFromUDP(data)
			if err != nil {
				Warning.Println("error during read:", err)
				continue
			}
			s := string(data[:n])
			Info.Printf("receive %s %d bytes: %s\n", remoteAddr, n, s)
			id, recvnum := 0, 0
			_, err = fmt.Sscanf(s, "I'm %d,received %d packets:", &id, &recvnum)
			if err != nil {
				Warning.Println("error during Sscanf:", err)
				continue
			}
			recvid := strings.Fields(strings.Split(s, ":")[1])
			if recvnum != len(recvid) {
				Warning.Println("message format error") //id个数与接收到数据不符
				continue
			}
			recv_ch <- recvdata{id, recvid}
		}
	}
}

// 根据时隙表规则，设定以节点id为优先级 固定顺序的排列时隙表，举例 时隙为10
// 1收到 2 3：		顺序：1 2 3 1 2 3 1 2 3	1	1的时隙：0,3,6,9
// 7收到 8 9 4：	顺序：4 7 8 9 4 7 8 9 4 7	7的时隙：1,5,9
// 要推算节点 datas.id 的时隙分布，只要知道时隙个数，优先级排名(id越小，优先级越高)即可推算
func myschedule_create(slot int, datas recvdata) string {
	rank := 0
	for _, id := range datas.recvid {
		num, err := strconv.Atoi(id)
		if err != nil {
			Warning.Println(err)
			continue
		}
		if num < datas.id {
			rank++
		}
	}
	// 根据排名计算时隙位置并导出时隙字符串,num为该节点下网内存活节点个数
	// temp := []string{}
	num, temp := len(datas.recvid)+1, []string{}
	for i := rank; i < slot; i += num {
		temp = append(temp, strconv.Itoa(i))
	}
	newdata := strings.Join(temp, ",")
	return newdata
}

// 解析时隙文件参数
func schedule_Parse(filepath string) (filedata, error) {
	schedulefile, err := os.Open(filepath)
	if err != nil {
		return filedata{}, err
	}
	defer schedulefile.Close()
	schedule := bufio.NewScanner(schedulefile)

	linenum, slots := 0, 0
	basic := []string{
		"<emane-tdma-schedule >",
		// "<structure frames='1' slots='32' slotoverhead='40' slotduration='10000' bandwidth='1M'/>", //更新文件不需要这行
		"  <multiframe frequency='2.347G' power='10' class='0' datarate='10M'>", //根据实际读入值将改变
		"    <frame index='0'>",
		"      <slot index='' nodes=''\n      </slot>>", //根据实际值改变
		"    </frame>",
		"  </multiframe>",
		"</emane-tdma-schedule>",
	}
	scheduleSlot := make(map[int]string)
	for schedule.Scan() {
		if schedule.Text() == "    </frame>" {
			break
		}
		linenum++
		if linenum == 2 {
			s := strings.Fields(schedule.Text()[2:])
			slots, err = strconv.Atoi(strings.Split(s[2], "'")[1])
			// frames := strings.Split(s[1], "'")[1]
			// slotoverhead := strings.Split(s[3], "'")[1]
			// slotduration := strings.Split(s[4], "'")[1]
			// bandwidth := strings.Split(s[5], "'")[1]
			if err != nil {
				Error.Fatalln(err)
			}
		} else if linenum == 3 {
			basic[1] = schedule.Text()
		} else if linenum >= 5 && (linenum-5)&1 == 0 { //(linenum-5)%2 == 0
			s := strings.Split(schedule.Text()[6:], "'")
			i, err := strconv.Atoi(s[3])
			if err != nil {
				Warning.Println(err)
				continue
			}
			scheduleSlot[i] = s[1]
		}
	}
	if err := schedule.Err(); err != nil {
		return filedata{}, err
	}
	Info.Printf("解析数据成功,slots: %d, schdule:\n %s\n", slots, basic[1])
	return filedata{slots, basic, scheduleSlot}, err
}

/* 按照如下指定格式写入文件中：
<emane-tdma-schedule >
  <multiframe frequency='2.347G' power='10' class='0' datarate='10M'>
    <frame index='0'>
      <slot index='0,16,14,30' nodes='1'>
      </slot>
      <slot index='1,17,15,31' nodes='2'>
      </slot>
    </frame>
  </multiframe>
</emane-tdma-schedule>
*/
func write_schedule(filepath string, newdata []string) error {
	file, err := os.Create(filepath)
	if err != nil {
		return err
	}
	defer file.Close()
	writer := bufio.NewWriter(file)
	for _, str := range newdata {
		_, err = writer.WriteString(str + "\n")
	}
	//注意，bufio 通过flush操作将缓冲写入真实的文件的，在关闭文件之前先flush，否则会造成数据丢失的情况。
	writer.Flush()
	return err
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

func exec_schedule(upfile string) string {
	cmd := exec.Command("emaneevent-tdmaschedule", "-i", os.Args[1], upfile)
	stderr, err := cmd.StderrPipe() //创建tdmaschedule输出管道
	if err != nil {
		return "创建管道失败," + err.Error()
	}
	if err := cmd.Start(); err != nil {
		return "执行命令失败," + err.Error()
	}
	result, _ := ioutil.ReadAll(stderr) // 读取输出结果
	if resdata := string(result); resdata != "" {
		return "发布时隙表失败," + err.Error()
	}
	return ""
}
