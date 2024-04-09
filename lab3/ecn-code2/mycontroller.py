#!/usr/bin/env python3
import argparse
import os
import sys
from time import sleep

import grpc

# Import P4Runtime lib from parent utils dir
# Probably there's a better way of doing this.
sys.path.append(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 '../../utils/'))
import p4runtime_lib.bmv2
import p4runtime_lib.helper
from p4runtime_lib.error_utils import printGrpcError
from p4runtime_lib.switch import ShutdownAllSwitchConnections
def parse_ipv4(packet_data):
    # IPv4头部的偏移量（以太网头部长度为14字节）
    ipv4_offset = 14
    # IPv4头部的长度（单位：字节）
    ipv4_header_length = (packet_data[ipv4_offset] & 0x0F) * 4
    # ECN字段在IPv4头部中的偏移量
    ecn_offset = ipv4_offset + 1 # 这里假设ECN字段在IPv4头部的第二个字节

    # 从数据包字节流中读取ECN字段的值
    ecn_value = (packet_data[ecn_offset] & 0b11000000) >> 6 # 获取前两位表示ECN的值
    if ecn == 3:
        print("Receive response -----\nECN value:3\nCongestion happens!!\n")
    else:
        print("Receive response -----\nECN value:")
        print(ecn)
        print("\n")
#定义进行ipv4报文转发的流表项
def writeIpForwardRules(p4info_helper, ingress_sw, egress_sw, mymatch_fields,mydstaddr,myport):

    table_entry = p4info_helper.buildTableEntry(
        table_name="MyIngress.ipv4_lpm",
        match_fields={
            "hdr.ipv4.dstAddr": mymatch_fields
        },
        action_name="MyIngress.ipv4_forward",
        action_params={
            "dstAddr": mydstaddr,
            "port": myport
        })
    ingress_sw.WriteTableEntry(table_entry)


    print("Installed transit ipforward rule on %s" % ingress_sw.name )
 # 增加设置ecn阈值的表，通过控制面下发。
def fetch_responses(connection):
    try:
        for response in connection.stream_msg_resp:
            if response.WhichOneof("update") == "packet":
                packet_data = response.packet.payload
                # 解析 IPv4 头部并获取 ECN 值
                parse_ipv4(packet_data)
                # 根据 ECN 值进行逻辑处理

    except AttributeError as e:
        print("AttributeError:", e)
    except grpc.RpcError as e:
        printGrpcError(e)

def write_ecn_rules(p4info_helper, egress_sw,threshold):

    table_entry = p4info_helper.buildTableEntry(
        table_name="MyEgress.change_ecn_t",
        action_name="MyEgress.change_ecn",
        action_params={
            "num":threshold
        })
    egress_sw.WriteTableEntry(table_entry)


def main(p4info_file, bmv2_file_path):
    # Instantiate a P4Runtime helper from the p4info file
    helper = p4runtime_lib.helper.P4InfoHelper(p4info_file)
    try:
        #s1,s2,s3的配置信息
        switches = {
            's1': p4runtime_lib.bmv2.Bmv2SwitchConnection(
                name='s1', address='127.0.0.1:50051', device_id=0,
                proto_dump_file='logs/s1-p4runtime-requests.txt'),
            's2': p4runtime_lib.bmv2.Bmv2SwitchConnection(
                name='s2', address='127.0.0.1:50052', device_id=1,
                proto_dump_file='logs/s2-p4runtime-requests.txt'),
            's3': p4runtime_lib.bmv2.Bmv2SwitchConnection(
                name='s3', address='127.0.0.1:50053', device_id=2,
                proto_dump_file='logs/s3-p4runtime-requests.txt')
        }
        for switch in switches.values():
            switch.MasterArbitrationUpdate()


        ecn_threshold = eval(input("Please input the ECN threshold: "))

        for switch in switches.values():
            switch.SetForwardingPipelineConfig(p4info=helper.p4info, bmv2_json_file_path=bmv2_file_path)
        for name, switch in switches.items():
            write_ecn_rules(helper, switch, ecn_threshold)

        #s1的流规则
        writeIpForwardRules(helper, ingress_sw=switches['s1'], egress_sw=switches['s1'],mymatch_fields= ["10.0.1.1", 32],mydstaddr="08:00:00:00:01:01",myport=2)
        writeIpForwardRules(helper, ingress_sw=switches['s1'], egress_sw=switches['s1'],mymatch_fields= ["10.0.1.11", 32],mydstaddr="08:00:00:00:01:11",myport=1)
        writeIpForwardRules(helper, ingress_sw=switches['s1'], egress_sw=switches['s2'],mymatch_fields= ["10.0.2.0", 24],mydstaddr="08:00:00:00:02:00",myport=3)
        writeIpForwardRules(helper, ingress_sw=switches['s1'], egress_sw=switches['s3'],mymatch_fields= ["10.0.3.0", 24],mydstaddr="08:00:00:00:03:00",myport=4)

        #s2的流规则
        writeIpForwardRules(helper, ingress_sw=switches['s2'], egress_sw=switches['s2'],mymatch_fields= ["10.0.2.2", 32],mydstaddr="08:00:00:00:02:02",myport=2)
        writeIpForwardRules(helper, ingress_sw=switches['s2'], egress_sw=switches['s2'],mymatch_fields=["10.0.2.22", 32],mydstaddr="08:00:00:00:02:22",myport=1)
        writeIpForwardRules(helper, ingress_sw=switches['s2'], egress_sw=switches['s1'],mymatch_fields= ["10.0.1.0", 24],mydstaddr="08:00:00:00:01:00",myport=3)
        writeIpForwardRules(helper, ingress_sw=switches['s2'], egress_sw=switches['s3'],mymatch_fields=["10.0.3.0", 24],mydstaddr="08:00:00:00:03:00",myport=4)


         #s3的流规则
        writeIpForwardRules(helper, ingress_sw=switches['s3'], egress_sw=switches['s3'],mymatch_fields=["10.0.3.3", 32],mydstaddr="08:00:00:00:03:03",myport=1)
        writeIpForwardRules(helper, ingress_sw=switches['s3'], egress_sw=switches['s1'],mymatch_fields=["10.0.1.0", 24],mydstaddr="08:00:00:00:01:00",myport=2)
        writeIpForwardRules(helper, ingress_sw=switches['s3'], egress_sw=switches['s2'],mymatch_fields=["10.0.2.0", 24],mydstaddr="08:00:00:00:02:00",myport=3)

        entry = helper.buildCloneSessionEntry(100, [
            {"egress_port": 2, "instance": 1},
            {"egress_port": 252, "instance": 2}
            ])
        switches['s1'].WritePREEntry(entry)
        fetch_responses(switches['s1'])
    except KeyboardInterrupt:
        print(" Shutting down.")
    except grpc.RpcError as e:
        printGrpcError(e)
    ShutdownAllSwitchConnections()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='P4Runtime Controller')
    parser.add_argument('--p4info', help='p4info proto in text format from p4c',
                        type=str, action="store", required=False,
                        default='./build/ecn.p4.p4info.txt')
    parser.add_argument('--bmv2-json', help='BMv2 JSON file from p4c',
                        type=str, action="store", required=False,
                        default='./build/ecn.json')
    args = parser.parse_args()

    if not os.path.exists(args.p4info):
        parser.print_help()
        print("\np4info file not found: %s\nHave you run 'make'?" % args.p4info)
        parser.exit(1)
    if not os.path.exists(args.bmv2_json):
        parser.print_help()
        print("\nBMv2 JSON file not found: %s\nHave you run 'make'?" % args.bmv2_json)
        parser.exit(1)
    main(args.p4info, args.bmv2_json)
