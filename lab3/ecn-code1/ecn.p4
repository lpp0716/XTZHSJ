/* -*- P4_16 -*- */

// 引入 P4 核心库和 v1model，以便可以访问 v1model 中定义的控制平面构件
#include <core.p4>
#include <v1model.p4>

// 定义一些常量，例如 TCP 协议、IPv4 协议类型和 ECN 阈值
const bit<8>  TCP_PROTOCOL = 0x06;
const bit<16> TYPE_IPV4 = 0x800;
/*************************************************************************
*********************** H E A D E R S  ***********************************
*************************************************************************/

// 定义了用于包头的一些自定义类型
typedef bit<9>  egressSpec_t;
typedef bit<48> macAddr_t;
typedef bit<32> ip4Addr_t;

header ethernet_t {
    macAddr_t dstAddr;
    macAddr_t srcAddr;
    bit<16>   etherType;
}

header ipv4_t {
    bit<4>    version;
    bit<4>    ihl;
    bit<6>    diffserv;
    bit<2>    ecn;
    bit<16>   totalLen;
    bit<16>   identification;
    bit<3>    flags;
    bit<13>   fragOffset;
    bit<8>    ttl;
    bit<8>    protocol;
    bit<16>   hdrChecksum;
    ip4Addr_t srcAddr;
    ip4Addr_t dstAddr;
}

struct metadata {
    bit<19> ECN_THRESHOLD;
}

struct headers {
    ethernet_t   ethernet;
    ipv4_t       ipv4;
}

/*************************************************************************
*********************** P A R S E R  ***********************************
*************************************************************************/

// 定义了一个包解析器（parser），用于解析入站数据包并填充头部和元数据。
parser MyParser(packet_in packet,
                out headers hdr,
                inout metadata meta,
                inout standard_metadata_t standard_metadata) {

    // 定义解析状态机中的第一个状态（起始状态）。
    state start {
        transition parse_ethernet;
    }

    // 定义解析以太网帧的状态。
    state parse_ethernet {
        // 提取以太网帧头部。
        packet.extract(hdr.ethernet);

        // 根据以太网类型字段分支转到下一个状态。
        transition select(hdr.ethernet.etherType) {
            TYPE_IPV4: parse_ipv4;
            default: accept;
        }
    }

    // 定义解析 IPv4 数据包的状态。
    state parse_ipv4 {
        // 提取 IPv4 头部。
        packet.extract(hdr.ipv4);

        // 转到接受状态。
        transition accept;
    }
}


/*************************************************************************
************   C H E C K S U M    V E R I F I C A T I O N   *************
*************************************************************************/

// 定义了一个校验和验证控制器（control），用于验证入站数据包的校验和是否正确。
control MyVerifyChecksum(inout headers hdr, inout metadata meta) {   
    apply {  }
}


/*************************************************************************
**************  I N G R E S S   P R O C E S S I N G   *******************
*************************************************************************/

control MyIngress(inout headers hdr,
                  inout metadata meta,
                  inout standard_metadata_t standard_metadata) {
    // 定义一个名为drop的Action，用于将数据包标记为丢弃
    action drop() {
        mark_to_drop(standard_metadata);
    }
    // 定义一个名为ipv4_forward的Action，用于进行IPv4转发
    action ipv4_forward(macAddr_t dstAddr, egressSpec_t port) {
        // 设置出口端口和MAC地址
        standard_metadata.egress_spec = port;
        hdr.ethernet.srcAddr = hdr.ethernet.dstAddr;
        hdr.ethernet.dstAddr = dstAddr;
        // 减少TTL值
        hdr.ipv4.ttl = hdr.ipv4.ttl - 1;
    }
    // 定义一个名为ipv4_lpm的流表，用于进行IPv4最长前缀匹配
    table ipv4_lpm {
        key = {
            hdr.ipv4.dstAddr: lpm;
        }
        actions = {
            ipv4_forward;
            drop;
            NoAction;
        }
        size = 1024;
        default_action = NoAction();
    }
    // 在apply代码块中对数据包进行处理
    apply {
        // 判断是否为IPv4数据包
        if (hdr.ipv4.isValid()) {
            // 应用ipv4_lpm流表
            ipv4_lpm.apply();
        }
    }
}


/*************************************************************************
****************  E G R E S S   P R O C E S S I N G   *******************
*************************************************************************/
control MyEgress(inout headers hdr,
                 inout metadata meta,
                 inout standard_metadata_t standard_metadata) {
    // 定义一个名为mark_ecn的Action，用于设置ECN标志
    
    action mark_ecn() {
        hdr.ipv4.ecn = 3;
    }
    action change_ecn(bit<19> num){
        meta.ECN_THRESHOLD = num;
    }
    // 增加自定义ecn阈值，需要增加一个table表
    table change_ecn_t{
    	key={}
    	actions = {
    		change_ecn;
    	}
    }
    // 在apply代码块中对数据包进行处理
    apply {
        change_ecn_t.apply();
        // 判断是否需要设置ECN标志
        if (hdr.ipv4.ecn == 1 || hdr.ipv4.ecn == 2){
            if (standard_metadata.enq_qdepth >= meta.ECN_THRESHOLD){
                // 设置ECN标志
                mark_ecn();
            }
        }
    }
}


/*************************************************************************
*************   C H E C K S U M    C O M P U T A T I O N   **************
*************************************************************************/

control MyComputeChecksum(inout headers hdr, inout metadata meta) {
    // 这个控制器使用 "update_checksum" 函数计算IPv4头部校验和
    apply {
        update_checksum(
            hdr.ipv4.isValid(), // 检查IPv4头是否有效
            {
                hdr.ipv4.version, // IP 协议版本
                hdr.ipv4.ihl, // IP 头长度
                hdr.ipv4.diffserv, // 服务类型字段
                hdr.ipv4.ecn, // 显式拥塞通告（ECN）位
                hdr.ipv4.totalLen, // 数据报总长度
                hdr.ipv4.identification, // 包标识符
                hdr.ipv4.flags, // 标记字段
                hdr.ipv4.fragOffset, // 分片偏移量
                hdr.ipv4.ttl, // 存活时间
                hdr.ipv4.protocol, // 上层协议
                hdr.ipv4.srcAddr, // 源IP地址
                hdr.ipv4.dstAddr // 目的IP地址
            },
            hdr.ipv4.hdrChecksum, // 存储校验和的变量
            HashAlgorithm.csum16 // 使用16位的校验和算法
        );
    }
}

/*************************************************************************
***********************  D E P A R S E R  *******************************
*************************************************************************/

control MyDeparser(packet_out packet, in headers hdr) {
    // 这个控制器在发出的数据包中添加以太网和IPv4头部
    apply {
        packet.emit(hdr.ethernet); // 添加以太网头部
        packet.emit(hdr.ipv4); // 添加IPv4头部
    }
}

/*************************************************************************
***********************  S W I T C H  *******************************
*************************************************************************/

V1Switch(
    MyParser(),
    MyVerifyChecksum(),
    MyIngress(),
    MyEgress(),
    MyComputeChecksum(),
    MyDeparser()
) main;
