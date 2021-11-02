#!/home/lk233/.cache/pypoetry/virtualenvs/core-3XChpotV-py3.6/bin/python
"""
coresendmsg: utility for generating CORE messages
"""

import socket
import sys

from core.api.tlv import coreapi
from core.api.tlv.enumerations import CORE_API_PORT, MessageTypes, SessionTlvs
from core.emulator.enumerations import MessageFlags


def print_available_tlvs(t, tlv_class):
    """
    Print a TLV list.
    """
    print(f"TLVs available for {t} message:")
    for tlv in sorted([tlv for tlv in tlv_class.tlv_type_map], key=lambda x: x.name):
        print(tlv.name.lower())


def receive_message(sock):
    """
    Retrieve a message from a socket and return the CoreMessage object or
    None upon disconnect. Socket data beyond the first message is dropped.
    """
    try:
        # large receive buffer used for UDP sockets, instead of just receiving
        # the 4-byte header
        data = sock.recv(4096)
        msghdr = data[:coreapi.CoreMessage.header_len]
    except KeyboardInterrupt:
        print("CTRL+C pressed")
        sys.exit(1)

    if len(msghdr) == 0:
        return None

    msgdata = None
    msgtype, msgflags, msglen = coreapi.CoreMessage.unpack_header(msghdr)

    if msglen:
        msgdata = data[coreapi.CoreMessage.header_len:]
    try:
        msgcls = coreapi.CLASS_MAP[msgtype]
    except KeyError:
        msg = coreapi.CoreMessage(msgflags, msghdr, msgdata)
        msg.message_type = msgtype
        print(f"unimplemented CORE message type: {msg.type_str()}")
        return msg
    if len(data) > msglen + coreapi.CoreMessage.header_len:
        data_size = len(data) - (msglen + coreapi.CoreMessage.header_len)
        print(
            f"received a message of type {msgtype}, dropping {data_size} bytes of extra data")
    return msgcls(msgflags, msghdr, msgdata)


def connect_to_session(sock, requested):
    """
    Use Session Messages to retrieve the current list of sessions and
    connect to the first one.
    """
    # request the session list
    tlvdata = coreapi.CoreSessionTlv.pack(SessionTlvs.NUMBER.value, "")
    flags = MessageFlags.STRING.value
    smsg = coreapi.CoreSessionMessage.pack(flags, tlvdata)
    sock.sendall(smsg)

    print("waiting for session list...")
    smsgreply = receive_message(sock)
    if smsgreply is None:
        print("disconnected")
        return False

    sessstr = smsgreply.get_tlv(SessionTlvs.NUMBER.value)
    if sessstr is None:
        print("missing session numbers")
        return False

    # join the first session (that is not our own connection)
    tmp, localport = sock.getsockname()
    sessions = sessstr.split("|")
    sessions.remove(str(localport))
    if len(sessions) == 0:
        print("no sessions to join")
        return False

    if not requested:
        session = sessions[0]
    elif requested in sessions:
        session = requested
    else:
        print("requested session not found!")
        return False

    print(f"joining session: {session}")
    tlvdata = coreapi.CoreSessionTlv.pack(SessionTlvs.NUMBER.value, session)
    flags = MessageFlags.ADD.value
    smsg = coreapi.CoreSessionMessage.pack(flags, tlvdata)
    sock.sendall(smsg)
    return True


def receive_response(sock, opt):
    """
    Receive and print a CORE message from the given socket.
    """
    print("waiting for response...")
    msg = receive_message(sock)
    if msg is None:
        print(f"disconnected from {opt.address}:{opt.port}")
        sys.exit(0)
    print(f"received message: {msg}")


class opts(object):
    def __init__(self, address, port, protocol):
        self.address = address
        self.port = port
        self.protocol = protocol


def execcmd(msg: bytes, listen: bool):
    """
    构建发送特定api方法，使用udp，默认地址 localhost、4038port
    传参msg即为api指令，listen确定是否监听套接字返回值
    """
    myopt = opts("localhost", CORE_API_PORT, socket.SOCK_DGRAM)
    sock = socket.socket(socket.AF_INET, myopt.protocol)
    sock.setblocking(True)
    try:
        sock.connect((myopt.address, myopt.port))
    except Exception as e:
        print(f"Error connecting to {myopt.address}:{myopt.port}:\n\t{e}")
        sys.exit(1)

    sock.sendall(msg)
    if listen:
        receive_response(sock, myopt)
    sock.close()


def parseArgs(type: str, args: str):
    """
    解析指令生成对应flagdata tlvdata
    支持的 message types:
    node link execute register config file interface event session exception
    支持的 message flags (flags=f1,f2,...):
    none add delete cri local string text tty
    """

    type = type.lower()
    types = [message_type.name.lower() for message_type in MessageTypes]
    if type not in types:
        print(f"Unknown message type requested: {type}")
        return None
    message_type = MessageTypes[type.upper()]
    msg_cls = coreapi.CLASS_MAP[message_type.value]
    tlv_cls = msg_cls.tlv_class
    args = args.split()

    # build a message consisting of TLVs from "type=value" arguments
    flagstr = ""
    tlvdata = b""
    for a in args:
        typevalue = a.split("=")
        if len(typevalue) < 2:
            print(f"Use \"type=value\" syntax instead of \"{a}\".")
            return None
        tlv_typestr = typevalue[0].lower()
        tlv_valstr = "=".join(typevalue[1:])
        if tlv_typestr == "flags":
            flagstr = tlv_valstr
            continue
        try:
            tlv_type = tlv_cls.tlv_type_map[tlv_typestr.upper()]
            tlvdata += tlv_cls.pack_string(tlv_type.value, tlv_valstr)
        except KeyError:
            print(f"Unknown TLV: \"{tlv_typestr}\"")
            return None

    flags = 0
    for f in flagstr.split(","):
        if f == "":
            continue
        try:
            flag_enum = MessageFlags[f.upper()]
            n = flag_enum.value
            flags |= n
        except KeyError:
            print(f"Invalid flag \"{f}\".")
            return None

    msg = msg_cls.pack(flags, tlvdata)
    return msg


def shutdown():
    """
    发送关闭全部会话的msg
    """
    msg = parseArgs('session', 'flags=delete name="all"')
    if msg is None:
        return
    execcmd(msg, False)


# shutdown()
