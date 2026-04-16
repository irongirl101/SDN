from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER,MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet,ethernet
from ryu.lib.packet import ipv4

class SimpleLearningSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    def __init__(self,*args,**kwargs):
        super(SimpleLearningSwitch,self).__init__(*args,**kwargs)
        self.mac_to_port = {}
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self,ev):
    # init switch, install default flow rule to send to controller 
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

    # install table-miss flow entry - send unmatched packets to controller 
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath,0,match,actions)

    def add_flow(self,datapath,priority,match,actions):
    # installs a forwarding rule into switch flow table 
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

    # contruct flow_mod message 
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst,idle_timeout=30)
        datapath.send_msg(mod)
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)

    def _packet_in_handler(self,ev):
    # handles incoming packets, learns MACs, installs flow rules
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        dst = eth.dst
        src = eth.src
        if eth.ethertype == 0x88cc:
             return
        ip = pkt.get_protocol(ipv4.ipv4)
        if ip and ip.src == "10.0.0.1" and ip.dst == "10.0.0.2":
             self.logger.info("Blocking IP traffic h1 -> h2")
             return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {}) 
        self.logger.info(f"Switch {dpid}: learned {src} on port {in_port}")
    # learn MAC addresses and corresponding ingress port 
        self.mac_to_port[dpid][src] = in_port

    # decide action based on learned information 
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            actions = [parser.OFPActionOutput(out_port)]

    # install flow rule for future packets to this destination
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self.add_flow(datapath, 1, match, actions)

        else:
            out_port = ofproto.OFPP_FLOOD
            actions = [parser.OFPActionOutput(out_port)]
    # send packet
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
             data = msg.data
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)
