from itertools import cycle
from re import T
import pysoem
from INOV_PDO import InputPdo
from INOV_PDO import OutputPdo
import ctypes
import time
import threading

class MachineWork:
    def __init__(self,port):
        self._port = port
        self._master = pysoem.Master()
        self._master.in_op = False
        self._master.do_check_state = False
        self._pd_thread_stop_event = threading.Event()
        self._ch_thread_stop_event = threading.Event()

    def _device_config_func(self,slave_pos):
        device = self._master.slaves[slave_pos]
        device.sdo_write(0x60C5,0x0,bytes(ctypes.c_uint32(174762667)))
        device.sdo_write(0x60C6,0x0,bytes(ctypes.c_uint32(174762667)))
        device.sdo_write(0x6083,0x0,bytes(ctypes.c_uint32(174762666)))
        device.sdo_write(0x6084,0x0,bytes(ctypes.c_uint32(174762666)))
        device.sdo_write(0x607F,0x0,bytes(ctypes.c_uint32(104857600)))
 
        device.sdo_write(0x1C12,0x0,bytes(ctypes.c_uint8(0)))
        device.sdo_write(0x1C13,0x0,bytes(ctypes.c_uint8(0)))
        device.sdo_write(0x1600,0x0,bytes(ctypes.c_uint8(0)))

        device.sdo_write(0x1A00,0x0,bytes(ctypes.c_uint8(0)))

        device.sdo_write(0x1600,0x1,bytes(ctypes.c_uint32(1614807056)))#6040 c_word
        device.sdo_write(0x1600,0x2,bytes(ctypes.c_uint32(1616904200)))#6060 mode
        device.sdo_write(0x1600,0x3,bytes(ctypes.c_uint32(1618608160)))#607A t_pos
        device.sdo_write(0x1600,0x4,bytes(ctypes.c_uint32(1619066912)))#6081 t_speeed PP
        device.sdo_write(0x1600,0x4,bytes(ctypes.c_uint32(1627324448)))#60FF t_speeed PV
        

        device.sdo_write(0x1A00,0x1,bytes(ctypes.c_uint32(1614872592)))#6041 s_word
        device.sdo_write(0x1A00,0x2,bytes(ctypes.c_uint32(1617166368)))#6064 pos
        device.sdo_write(0x1A00,0x3,bytes(ctypes.c_uint32(1617690656)))#606C speed

        device.sdo_write(0x1600,0x0,bytes(ctypes.c_uint8(4)))
        device.sdo_write(0x1A00,0x0,bytes(ctypes.c_uint8(3)))

        device.sdo_write(0x1C12,0x1,bytes(ctypes.c_uint16(5632))) #1600
        device.sdo_write(0x1C13,0x1,bytes(ctypes.c_uint16(6656))) #1A00

        device.sdo_write(0x1C12,0x0,bytes(ctypes.c_uint8(1)))
        device.sdo_write(0x1C13,0x0,bytes(ctypes.c_uint8(1)))

        self.slave1.dc_sync(1, 10000000)

    def _convert_input_data(self,data):
        return InputPdo.from_buffer_copy(data)

    def setup(self):
        self._master.open(self._port)
        if not self._master.config_init() > 0:
            self._master.close()
            raise HandleError('no slave found')

        self.slave1 = self._master.slaves[0]
        self.slave1.config_func = self._device_config_func
        self._master.config_overlap_map()
        self._master.config_dc()
        
        if self._master.state_check(pysoem.SAFEOP_STATE, 50000) != pysoem.SAFEOP_STATE:
            self._master.close()
            raise HandleError('not all slaves reached SAFEOP state')
        
        self._master.state = pysoem.OP_STATE

        self.check_thread = threading.Thread(target=self._check_thread)
        self.check_thread.start()
        self.proc_thread = threading.Thread(target=self._processdata_thread)
        self.proc_thread.start()


        # send one valid process data to make outputs in slaves happy
        self._master.send_overlap_processdata()
        wkc = self._master.receive_processdata(2000)

        self._master.write_state()
        self.all_slaves_reached_op_state = False
        
        for i in range(40):
            self._master.state_check(pysoem.OP_STATE, 50000)
            if self._master.state == pysoem.OP_STATE:
                self.all_slaves_reached_op_state = True
                break
            

        if self.all_slaves_reached_op_state:
            output_data = OutputPdo()
            try:

                self.slave1.sdo_write(0x2002,0x1,bytes(ctypes.c_uint16(9)))# 0 speed; 1 position; 2 t; 9 ethercat
                time.sleep(0.5)

                
                output_data.Target_Position = 100000000
                output_data.target_speed_pp = 174762
                self.slave1.output = bytes(output_data)
                time.sleep(0.02)
                for cmd in [6,47,63]:
                    output_data.Control_Word = cmd
                    self.slave1.output = bytes(output_data)
                    time.sleep(0.02)
                    print('status_word',cmd,self._convert_input_data(self.slave1.input).status_word)

                while True:
                    print(str(self._convert_input_data(self.slave1.input).actual_speed))
                    time.sleep(0.1)

       
                # zero everything
                self.slave1.output = bytes(len(self.slave1.output))
                time.sleep(1)

            except KeyboardInterrupt:

                output_data.Control_Word = 7
                self.slave1.output = bytes(output_data)
                time.sleep(0.02)

                # zero everything
                self.slave1.output = bytes(len(self.slave1.output))
                time.sleep(1)

                
              
        else:
            print('al status code {} ({})'.format(hex(self.slave1.al_status), pysoem.al_status_code_to_string(self.slave1.al_status)))
            print('failed to got to OP_STATE')
            
        
        self._pd_thread_stop_event.set()
        self._ch_thread_stop_event.set()
        self.proc_thread.join()
        self.check_thread.join()

        self._master.state = pysoem.INIT_STATE
        self._master.write_state()
        self._master.close()  
    
    def _check_thread(self):
        while not self._ch_thread_stop_event.is_set():
            if self._master.in_op and ((self._actual_wkc < self._master.expected_wkc) or self._master.do_check_state):
                print('checking')
                self._master.do_check_state = False
                self._master.read_state()
                for i, slave in enumerate(self._master.slaves):
                    if slave.state != pysoem.OP_STATE:
                        self._master.do_check_state = True
                        MachineWork._check_slave(slave, i)
                if not self._master.do_check_state:
                    print('OK : all slaves resumed OPERATIONAL.')
            time.sleep(0.01)

    def _processdata_thread(self):
        while not self._pd_thread_stop_event.is_set():
            self._master.send_overlap_processdata()
            self._actual_wkc = self._master.receive_processdata(10000)
            if not self._actual_wkc == self._master.expected_wkc:
                print('incorrect wkc',self._actual_wkc,self._master.expected_wkc)
            time.sleep(0.01)
    
    @staticmethod
    def _check_slave(slave, pos):
        if slave.state == (pysoem.SAFEOP_STATE + pysoem.STATE_ERROR):
            print(
                'ERROR : slave {} is in SAFE_OP + ERROR, attempting ack.'.format(pos))
            slave.state = pysoem.SAFEOP_STATE + pysoem.STATE_ACK
            slave.write_state()
        elif slave.state == pysoem.SAFEOP_STATE:
            print(
                'WARNING : slave {} is in SAFE_OP, try change to OPERATIONAL.'.format(pos))
            slave.state = pysoem.OP_STATE
            slave.write_state()
        elif slave.state > pysoem.NONE_STATE:
            if slave.reconfig():
                slave.is_lost = False
                print('MESSAGE : slave {} reconfigured'.format(pos))
        elif not slave.is_lost:
            slave.state_check(pysoem.OP_STATE)
            if slave.state == pysoem.NONE_STATE:
                slave.is_lost = True
                print('ERROR : slave {} lost'.format(pos))
        if slave.is_lost:
            if slave.state == pysoem.NONE_STATE:
                if slave.recover():
                    slave.is_lost = False
                    print(
                        'MESSAGE : slave {} recovered'.format(pos))
            else:
                slave.is_lost = False
                print('MESSAGE : slave {} found'.format(pos))

class HandleError(Exception):
    def __init__(self, message):
        super(HandleError, self).__init__(message)
        self.message = message

port = '\\Device\\NPF_{267091CF-E38D-4EED-AAC8-1A0692194D59}'
machine = MachineWork(port)
machine.setup()
