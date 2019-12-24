#//----------------------------------------------------------------------
#//   Copyright 2007-2010 Mentor Graphics Corporation
#//   Copyright 2007-2011 Cadence Design Systems, Inc.
#//   Copyright 2010 Synopsys, Inc.
#//   Copyright 2019 Tuomas Poikela (tpoikela)
#//   All Rights Reserved Worldwide
#//
#//   Licensed under the Apache License, Version 2.0 (the
#//   "License"); you may not use this file except in
#//   compliance with the License.  You may obtain a copy of
#//   the License at
#//
#//       http://www.apache.org/licenses/LICENSE-2.0
#//
#//   Unless required by applicable law or agreed to in
#//   writing, software distributed under the License is
#//   distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
#//   CONDITIONS OF ANY KIND, either express or implied.  See
#//   the License for the specific language governing
#//   permissions and limitations under the License.
#//----------------------------------------------------------------------

import cocotb
from cocotb.triggers import RisingEdge, Timer

from uvm.base import *
from uvm.comps import UVMDriver
from uvm.macros import uvm_component_utils
from ubus_transfer import *

#//------------------------------------------------------------------------------
#//
#// CLASS: ubus_master_driver
#//
#//------------------------------------------------------------------------------

class ubus_master_driver(UVMDriver):
    #
    #  // The virtual interface used to drive and view HDL signals.
    #  protected virtual ubus_if vifg
    #
    #  // Master Id
    #  protected int master_idg
    #

    #  // Provide implmentations of virtual methods such as get_type_name and create
    #  `uvm_component_utils_begin(ubus_master_driver)
    #    `uvm_field_int(master_id, UVM_DEFAULT)
    #  `uvm_component_utils_end

    def __init__(self, name, parent):
        UVMDriver.__init__(self, name, parent)
        # The virtual interface used to drive and view HDL signals.
        self.vif = None
        self.master_id = 0


    def build_phase(self, phase):
        arr = []
        if UVMConfigDb.get(self, "", "vif", arr):
            self.vif = arr[0]
        if self.vif is None:
            self.uvm_report_fatal("NOVIF", "virtual interface must be set for: " +
                self.get_full_name() + ".vif")


    @cocotb.coroutine
    def run_phase(self, phase):
        #    fork
        fork_get = cocotb.fork(self.get_and_drive())
        fork_reset = cocotb.fork(self.reset_signals())
        yield [fork_get, fork_reset.join()]
        #    join


    #  // get_and_drive
    #  virtual protected task get_and_drive()g
    @cocotb.coroutine
    def get_and_drive(self):
        print("EEE get_and_drive started")
        # @(negedge vif.sig_reset)g
        yield RisingEdge(self.vif.sig_reset)
        print("EEE got posedge reset")
        while True:
            yield RisingEdge(self.vif.sig_clock)
            print("EEE got rising edge")
            req = []
            yield self.seq_item_port.get_next_item(req)
            print("EEE got  item from seq port")
            #$cast(rsp, req.clone())g
            rsp = req[0].clone()
            rsp.set_id_info(req[0])
            yield self.drive_transfer(rsp)
            self.seq_item_port.item_done()
            self.seq_item_port.put_response(rsp)
        #  endtask : get_and_drive


    #  // reset_signals
    @cocotb.coroutine
    def reset_signals(self):
        while True:
            yield RisingEdge(self.vif.sig_reset)
            self.vif.rw = 0
            self.vif.sig_request <= 0
            self.vif.sig_addr           <= 0
            self.vif.sig_data_out       <= 0
            self.vif.sig_size           <= 0
            self.vif.sig_read           <= 0
            self.vif.sig_write          <= 0
            self.vif.sig_bip            <= 0
        #  endtask : reset_signals

    #  // drive_transfer
    #  virtual protected task drive_transfer (ubus_transfer trans)g
    @cocotb.coroutine
    def drive_transfer(self, trans):
        if trans.transmit_delay > 0:
            for i in range(trans.transmit_delay):
                yield RisingEdge(self.vif.sig_clock)
        yield self.arbitrate_for_bus()
        yield self.drive_address_phase(trans)
        yield self.drive_data_phase(trans)
        #  endtask : drive_transfer


    def get_req_val(self, val):
        req_val = self.vif.sig_request.value.get_value()
        if val == 1:
            req_val = req_val | (1 << self.master_id)
        else:
            print("get_req_val read val " + str(req_val))
            req_val = req_val & ~(1 << self.master_id) & 0xFFFF
        return req_val

    #  // arbitrate_for_bus
    @cocotb.coroutine
    def arbitrate_for_bus(self):
        self.vif.sig_request <= self.get_req_val(1)
        while True:
            yield RisingEdge(self.vif.sig_clock)
            #grant_val = self.vif.sig_grant.value[self.master_id]
            grant_val = self.vif.sig_grant.value[self.master_id]
            if grant_val != 0:
                break
        self.vif.sig_request <= self.get_req_val(0)
        #  endtask : arbitrate_for_bus

    def is_grant_ok(self, grant_val):
        idx = self.master_id
        mask = 1 << idx
        result = mask & grant_val
        return result != 0

    #
    #  // drive_address_phase
    @cocotb.coroutine
    def drive_address_phase(self, trans):
        self.vif.sig_addr <= trans.addr
        self.drive_size(trans.size)
        self.drive_read_write(trans.read_write)
        yield RisingEdge(self.vif.sig_clock)
        #self.vif.sig_addr <= 32'bzg
        self.vif.sig_addr <= 0
        self.vif.sig_size <= 0
        self.vif.sig_read <= 0
        self.vif.sig_write <= 0
        #  endtask : drive_address_phase

    #
    #  // drive_data_phase
    @cocotb.coroutine
    def drive_data_phase (self, trans):
        err = 0
        for i in range(trans.size):
            if (i == (trans.size - 1)):
                self.vif.sig_bip <= 0
            else:
                self.vif.sig_bip <= 1
            if (trans.read_write == READ):
                yield self.read_byte(trans.data[i], err)
            else:
                yield self.write_byte(trans.data[i], err)
        self.vif.sig_data_out <= 0
        self.vif.sig_bip <= 0
        #  endtask : drive_data_phase


    #  // read_byte
    @cocotb.coroutine
    def read_byte(self, data, error):
        self.vif.rw <= 0
        while True:
            yield RisingEdge(self.vif.sig_clock)
            if self.vif.sig_wait == 0:
                break
        data.append(self.vif.sig_data.value)
        #  endtask : read_byte


    #  // write_byte
    @cocotb.coroutine
    def write_byte(self, data, error):
        self.vif.rw <= 1
        self.vif.sig_data_out <= data
        while True:
            yield RisingEdge(self.vif.sig_clock)
            if self.vif.sig_wait == 0:
                break
        self.vif.rw <= 0
        #  endtask : write_byte

    #
    #  // drive_size
    def drive_size(self, size):
        #case (size)
        if size == 1:
            self.vif.sig_size <= 0
        elif size == 2:
            self.vif.sig_size <= 1
        elif size == 4:
            self.vif.sig_size <= 2
        elif size == 8:
            self.vif.sig_size <= 3
        #endcase
        #  endtask : drive_size

    #
    #  // drive_read_write
    def drive_read_write(self, rw):
        #case (rw)
        if rw == NOP:
            self.vif.sig_read <= 0
            self.vif.sig_write <= 0
        elif rw == READ:
            self.vif.sig_read <= 1
            self.vif.sig_write <= 0
        elif rw == WRITE:
            self.vif.sig_read <= 0
            self.vif.sig_write <= 1
        #endcase
    #  endtask : drive_read_write

    #
    #endclass : ubus_master_driver
uvm_component_utils(ubus_master_driver)