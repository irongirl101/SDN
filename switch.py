from ryu.base import app_manager # base class for ryu apps 
from ryu.controller import ofp_event # OpenFlow event definitions
from ryu.controller.handler import CONFIG_DISPATCHER,MAIN_DISPATCHER 
from ryu.controller.handler import set_ev_cls # decorator to bind events to handlers
from ryu.ofproto import ofproto_v1_3 #OpenFlow 1.3 protocol
from ryu.lib.packet import packet,ethernet # packet parsing utils
from ryu.lib.packet import ipv4 # used for blocking 

class SimpleLearningSwitch(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION] # specify openFlow version (1.3)
    def __init__(self,*args,**kwargs):
        super(SimpleLearningSwitch,self).__init__(*args,**kwargs)
        self.mac_to_port = {} # dict 
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features(self,ev):
    # init switch, install default flow rule to send to controller 
        datapath = ev.msg.datapath # switch datapath object
        ofproto = datapath.ofproto # OpenFlow protocol constants
        parser = datapath.ofproto_parser # parser to create OpenFlow messages

    # install table-miss flow entry - send unmatched packets to controller 
        match = parser.OFPMatch() # Empty match = match all packets
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,ofproto.OFPCML_NO_BUFFER)] # Send to controller - do not buffer packet
        self.add_flow(datapath,0,match,actions) # install rules with priority 0 

    def add_flow(self,datapath,priority,match,actions):
    # installs a forwarding rule into switch flow table 
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

    # contruct flow_mod message 
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst,idle_timeout=30) #create FlowMod message (rule to install)
        datapath.send_msg(mod) # send rule to switch
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)

    def _packet_in_handler(self,ev):
    # handles incoming packets, learns MACs, installs flow rules
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port'] # port where packet entered switch

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0] # extract eth header 

        dst = eth.dst #dest mac
        src = eth.src # src mac

        if eth.ethertype == 0x88cc: # ignore LLDP packets -> used internally by SDN tools
             return
        
        #blocking policy based 
        ip = pkt.get_protocol(ipv4.ipv4)
        if ip and ip.src == "10.0.0.1" and ip.dst == "10.0.0.2":
             self.logger.info("Blocking IP traffic h1 -> h2")
             return # Drop packet (no forwarding)

        dpid = datapath.id #switch id 
        self.mac_to_port.setdefault(dpid, {})  #init table for switch 

        # log learning event
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
        # Unknown destination -> flood to all ports
        else:
            out_port = ofproto.OFPP_FLOOD
            actions = [parser.OFPActionOutput(out_port)]
    # send packet
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER: # include packet data if not buffered
             data = msg.data
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out) # send packet to switch
