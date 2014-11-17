#!/usr/bin/env python
"""
Copyright (C) 2012 bendikro

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

"""
This program runs a sequence of commands on remote hosts using SSH.
"""
import itertools
import pprint
import sys
import math
import argparse
import os
from copy import deepcopy

import scheduler
from scheduler import cprint

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

    def copy(self):
        new = AttrDict(self.__dict__)
        return new

class TestProperties(dict):
    def __init__(self, *args, **kwargs):
        super(TestProperties, self).__init__(*args, **kwargs)
        self.__dict__ = self

"""
    #delay_between_jobs_seconds = 2
    #job_duration_minutes = [30, 60, 120]
    #job_duration_minutes = [10, 20]
    #job_duration_minutes = [10, 15, 20, 30]
    #job_duration_minutes = [20]
    #job_duration_minutes = [15, 30]
    #job_duration_minutes = [45, 60]
    #job_duration_minutes = [15]

    queue_types = ["pfifo"]
    rdb_option = [False]
    # Create session jobs from all variations of the following options:
    loss_values = [""]
    #rdb_option = [False, True]
    #payload_values = [100]
    payload_values = [100, 300, 500]
    #stream_count_values = [1, 32, 128, 512]
    #stream_count_values = [50, 64, 90]
    #stream_count_values = [8, 16]
    stream_count_values = [8]

    #loss_values = ["0.5", "5", "fixedv 7,8,9,11,15,16,17,18,19,20,30 40"]
    itt_values = [50, 100, 200]
    rtt_values = [30, 100, 200]

    #rtt_values = [100, 200]
    packets_in_flight_rdb_limit = [3, 6, 10]
    #packets_in_flight_rdb_limit = [3]

    segmentation_types = ["tso", "gso", "gro", "lro"]

    thin_dupack = [0]
    thin_linear = [0]
    #itt_values = [100]
    #rtt_values = [150]
    retrans_collapse_thin = [0]
    retrans_collapse_thick = [0]
    segmentation_offload = ["off"]
    segmentation_offload_thin = [#{"default" : "off", "tso": "on"},
                                 #{"default" : "off", "gso": "on"},
                                 #{"default" : "off", "gro": "on"},
                                 #{"default" : "off", "lro": "on"},
                                 #{"default" : "off", "tso": "on", "gso": "on"},

                                 #{"default" : "off", "tso": "on", "gso": "on", "gro": "on"},
                                 #{"default" : "off", "tso": "on", "gso": "on", "lro": "on"},
                                 #{"default" : "off", "tso": "on", "gso": "on", "gro": "on", "lro": "on"},
                                 #{"default" : "off", "tso": "on", "gro": "on"},
                                 #{"default" : "off", "tso": "on", "gro": "on", "lro": "on"},
                                 #{"default" : "off", "gso": "on", "gro": "on"},
                                 #{"default" : "off", "gso": "on", "gro": "on", "lro": "on"},
                                 #{"default" : "on", "tso": "off"},
                                 #{"default" : "on", "gso": "off"},
                                 #{"default" : "on", "gro": "off"},
                                 #{"default" : "on", "lro": "off"},
                                 #{"default" : "on", "tso": "off", "gso": "off"},
                                 "on",
                                 #"off"
                                 ]
    segmentation_offload_thick = ["off"]
    #segmentation_offload_thin = ["on"]
    segmentation_offload_thin = ["off"]

    #segmentation_offload = ["off", "on"]

    #segmentation_offload_thin = ["on", "off"]
    #segmentation_offload_thick = ["on", "off"]
    #retrans_collapse_thin = ["0", "1"]
    #retrans_collapse_thin = ["1"]
    #retrans_collapse_thin = ["0"]
    #retrans_collapse_thick = ["0", "1"]

    bridge_interface_speeds = ["speed 10 duplex full"]
    bridge_interface_speeds = [None]

    # Small tests
    bandwidth_rate_cap_kbit = 5000
    #job_duration_minutes = [10, 20, 40]
    job_duration_minutes = [10]
    #stream_count_values = [5, 10, 20]
    #stream_count_values = [30, 60]
    #stream_count_values = [15]
    thick_stream_count_values = [10]
    #thin_stream_count_values = [15, 60]
    #thin_stream_count_values = [15, 30]

    #thin_stream_count_values = [50]
    payload_values = [120]
    #itt_values = [100, 150]
    #itt_values = ["200:20", "100:10"]
    rtt_values = [150]
    ramp_up_times = ["13:2"]
    #ramp_up_times = ["100"]
    #rdb_option = [False, True]
    #packets_in_flight_rdb_limit = [3, 6, 10]

    #test_count = [0,1,2,3,4]
    #test_count = [0,1]
    test_count = [0]

    # Initial tests
    job_duration_minutes = [5]
    #delay_between_jobs_seconds = 1

    #queue_types = ["pfifo", "bfifo"]
    queue_types = ["pfifo"]
    rdb_option = [False, True]
    #rdb_option = [False]
    #thick_stream_count_values = [5, 10]
    thick_stream_count_values = [10]
    thin_stream_count_values = range(1, 30, 5)
    stream_count_values = zip(thin_stream_count_values, thin_stream_count_values)

    #thin_stream_count_values = [21]
    #packets_in_flight_rdb_limit = [20, 4]
    packets_in_flight_rdb_limit = [4, 20, 100]
    #itt_values = ["40:10", "60:10"]
    #itt_values = ["60"]
    rtt_values = [150]

#    # CONG WIN TESTING
#    #delay_between_jobs_seconds = 300
#    job_duration_minutes = [10]
#    #queue_types = ["pfifo", "bfifo"]
#    queue_types = ["pfifo"]
#    rdb_option = [False, True]
#    rdb_option = [True]
#    thick_stream_count_values = [2]
#    thin_stream_count_values = [2]
#    #packets_in_flight_rdb_limit = [4, 20, 300]
#    packets_in_flight_rdb_limit = [300]
#    ramp_up_times = ["20:5"]
#    #itt_values = [1, 2, 8, 32, 64]
#    itt_values = [40]
#    #itt_values = [1]
#    rtt_values = [150]
#    payload_values = [700]
#
    itt_values = [1, 10, 20]
    itt_values = [10]
    payload_values = [400]
    test_count = [0, 1, 2, 3]
    test_count = [0]
    #thin_dupack = [1]
    #thin_dupack = [0, 1]
    #thin_linear = [0, 1]

    #itt_values = [100]
    #itt_values = ["100:10"]
    #payload_values = [120]
    stream_count = 10
    max_streams = max(stream_count + 1, 22)
"""

def main():
    argparser = argparse.ArgumentParser(description="Run test sessions")
    argparser.add_argument("-p", "--print-dictionary",  help="Print the session dictionary and exit instead of running the jobs.", action='store_true', required=False)
    argparser.add_argument("-pn", "--print-job-names",  help="Print the list of job names (ids).", action='store_true', required=False)
    args = scheduler.parse_args(argparser)
    abort = False

    def make_stream(base={}, streams=[1], **kw):
        return [AttrDict(base, stream_count=i, **kw) for i in streams]

    start_port = {"thick": 12000, "thin": 22000, "thin2": 22000, "thin3": 32000}
    custom_session_settings = {}
    custom_settings = {"gather_results_on_cancel": False}
    segmentation_types = ["tso", "gso", "gro", "lro"]

    dp = default_test_properties = TestProperties()
    dp.job_duration_minutes = [5]
    dp.delay_between_jobs_seconds = 300
    dp.bandwidth_rate_cap_kbit = 5000
    dp.test_count = [0]
    dp.packets_in_flight_rdb_limit = [0]
    dp.rdb_option = [False]
    dp.cong_thin = ["cubic"]
    dp.loss_values = [""]
    dp.itt_values = [100]
    dp.rtt_values = [150]
    dp.segmentation_offload_thick = ["off"]
    dp.segmentation_offload_thin = ["off"]
    dp.segmentation_offload = ["off"]
    dp.retrans_collapse_thin = [0]
    dp.retrans_collapse_thick = [0]
    dp.bridge_interface_speeds = [None]
    dp.ramp_up_times = ["13:2"]
    dp.queue_types = ["pfifo"]
    dp.tfrc = [0]
    dp.thin_dupack = [0]
    dp.thin_linear = [0]
    dp.early_retr = [3]
    dp.tcp_args_options = []
    dp.queue_limit = [None]
    dp.abuser = [False]

    ##############################
    ##############################
    # TFRC testing
    ##############################
    def module_testing():
        p = TestProperties(default_test_properties)
        p.job_duration_minutes = [15]
        p.delay_between_jobs_seconds = 1
        p.cong_other = "cubic"
        p.queue_limit = [60]
        #p.cong_thin = ["rdb"]
        p.cong_thin = ["cubic"]
        p.default_options = { "thin": { "cong": "cubic"}, "thin2": { "cong": "cubic" } }
        p.rdb_option = [
            #True,
            #"dpif",
            False
        ]
        #p.tcp_args_options = [
        #    { "thin": {"thin_dupack": 0, "thin_linear": 0, "early_retr": 3 } },
        #    { "thin": {"thin_dupack": 1, "thin_linear": 1, "early_retr": 3 } },
        #    { "thin": {"thin_dupack": 1, "thin_linear": 1, "early_retr": 0 } },
        #    #{ "thin": {"thin_dupack": 0, "thin_linear": 0, "early_retr": 0 } },
        #]
        p.payload_values = [120]
        p.tfrc = [1]
        p.dpif_lim = [10]
        defult_conf = {"cong": "cubic"}
        p.itt_values = ["10:1"]
        p.thin_args = dict(defult_conf, name="thin", prefix="y")
        p.packets_in_flight_rdb_limit = [100]
        p.stream_count = 30
        max_streams = p.stream_count + 1
        thin_range = range(30, max_streams, 10)
        thin_stream_count_values =  make_stream(p.thin_args, streams=thin_range)
        #print "thin_stream_count_values:", thin_stream_count_values
        #thin2_stream_count_values = make_stream(name="thin2", prefix="y", streams=thin_range)
        #thick_streams = [5] * len(thin_stream_count_values)
        thick_streams = range(5, max_streams, 5)
        #print "thin_stream_count_values:", len(thin_stream_count_values)

        thick_stream_count_values = make_stream(name="thick", prefix="z", streams=thick_streams)
        p.streams = zip(thin_stream_count_values, thick_stream_count_values)
        #p.streams = zip(thin_stream_count_values, thin2_stream_count_values, thick_stream_count_values)
        return p


    ##############################
    ##############################
    # TFRC testing
    ##############################
    def TFRC_RDB_vs_greedy_tests():
        p = TestProperties(default_test_properties)
        p.job_duration_minutes = [5]
        #p.bandwidth_rate_cap_kbit = 1000
        p.delay_between_jobs_seconds = 120
        p.cong_other = "cubic"
        p.queue_limit = [120, 60]
        p.queue_limit = [60]
        #p.rdb_option = [True, False]
        #p.cong_thin = ["rdb"]
        p.cong_thin = ["cubic"]
        p.default_options = { "thin": { "cong": "cubic"}, "thin2": { "cong": "cubic" } }
        p.rdb_option = [
            #True,
            "dpif",
            #False
        ]
        p.tcp_args_options = [
            { "thin": {"thin_dupack": 0, "thin_linear": 0, "early_retr": 3 } },
            { "thin": {"thin_dupack": 1, "thin_linear": 1, "early_retr": 3 } },
            #{ "thin": {"thin_dupack": 1, "thin_linear": 1, "early_retr": 0 } },

            #{ "thin": {"thin_dupack": 0, "thin_linear": 0, "early_retr": 0 } },
        ]
        p.payload_values = [120]
        #p.thin_dupack = [1]
        #p.thin_linear = [1]
        #p.early_retr = [1]
        p.tfrc = [1, 0]
        #p.tfrc = [0]
        p.dpif_lim = [10, 20]
        p.dpif_lim = [10]
        defult_conf = {"cong": "rdb"}
        #defult_conf = {}
        #p.itt_values = ["10:1", "30:3", "50:5", "100:10"] # "75:7", "50:5",
        p.itt_values = ["10:1", "30:3", "75:7", "100:10"] # "75:7", "50:5",
        p.itt_values = ["10:1"] # "75:7", "50:5",
        p.thin_args = dict(defult_conf, name="thin", prefix="r")
        p.packets_in_flight_rdb_limit = [100]
        p.stream_count = 20
        #p.stream_count = 10
        max_streams = p.stream_count + 1
        #thin_range = range(10, max_streams, 10)
        thin_range = [5, 10, 20]
        thin_range = [10]
        thin_stream_count_values =  make_stream(p.thin_args, streams=thin_range)
        print "thin_stream_count_values:", thin_stream_count_values
        thin2_stream_count_values = make_stream(name="thin2", prefix="w", streams=thin_range)
        thick_streams = [5] * len(thin_stream_count_values)
        #thick_streams = range(5, max_streams, 5)
        print "thin_stream_count_values:", len(thin_stream_count_values)

        thick_stream_count_values = make_stream(name="thick", prefix="z", streams=thick_streams)
        #print "thick_stream_count_values:", len(thick_stream_count_values)
        #p.streams = zip(thin_stream_count_values, thick_stream_count_values)
        p.streams = zip(thin_stream_count_values, thin2_stream_count_values, thick_stream_count_values)
        #p.streams = [thin_stream_count_values]
        return p

    ##############################
    ##############################
    # RDB vs Greedy tests
    ##############################
    def RDB_vs_greedy_tests():
        p = TestProperties(default_test_properties)
        p.job_duration_minutes = [20]
        p.job_duration_minutes = [5, 10]
        p.delay_between_jobs_seconds = 300
        #p.delay_between_jobs_seconds = 1
        p.cong_other = "cubic"
        p.cong_thin = ["cubic"]
        p.rdb_option = [
            True,
            "dpif",
            False
        ]
        p.tcp_args_options = [
            {"thin_dupack": 0, "thin_linear": 0, "early_retr": 3 },
            {"thin_dupack": 1, "thin_linear": 1, "early_retr": 3 },
            {"thin_dupack": 1, "thin_linear": 1, "early_retr": 0 },
            {"thin_dupack": 0, "thin_linear": 0, "early_retr": 0 },
        ]
        #p.rdb_option = [False]
        p.payload_values = [120]
        p.thin_dupack = [0]
        p.thin_linear = [0]
        #p.early_retr = [1]
        p.tfrc = [0]
        #defult_conf = {"cong": "cubic"}
        #defult_conf = {"cong": "rdb"}
        defult_conf = {}
        #p.loss_values = ["0.5", "5"]
        #p.loss_values = ["10", "5", "2", "0.5"]
        p.itt_values = ["100:10", "50:5", "30:3", "10:1"] # "75:7", "50:5",
        #p.itt_values = ["10:1"]
        p.test_count = [0]

        p.thin_args = dict(defult_conf, name="thin", prefix="r")
        p.packets_in_flight_rdb_limit = [4, 8, 12, 15, 20]
        p.dpif_lim = [10, 20]

        p.packets_in_flight_rdb_limit = [8]
        p.stream_count = 10
        max_streams = max(p.stream_count + 1, 10)
        thin_stream_count_values =  make_stream(p.thin_args, streams=range(10, max_streams, 5))

        thick_streams = [10] * len(thin_stream_count_values)
        print "thin_stream_count_values:", len(thin_stream_count_values)
        #thin2_stream_count_values = make_stream(name="thin2", prefix="y", sr=(p.stream_count, max_streams, 10))
        thick_stream_count_values = make_stream(name="thick", prefix="z", streams=thick_streams)
        #thick_stream_count_values = make_stream(name="thick", prefix="z", streams=range(5, max_streams, 5))
        #print "thick_stream_count_values:", len(thick_stream_count_values)
        p.streams = zip(thin_stream_count_values, thick_stream_count_values)
        return p

    ##############################
    ##############################
    # RDB vs Greedy tests
    ##############################
    def RDB_vs_greedy_misuse_tests():
        p = TestProperties(default_test_properties)
        p.job_duration_minutes = [20]
        p.delay_between_jobs_seconds = 300
        #p.delay_between_jobs_seconds = 1
        p.cong_other = "cubic"
        p.cong_thin = ["rdb"]
        p.default_options = { "thin": { "cong": "cubic", "abuser": "800"}, "thin2": { "cong": "cubic" } }
        p.rdb_option = [
            #True,
            "dpif",
            #False
        ]
        p.tcp_args_options = [
            {"thin_dupack": 0, "thin_linear": 0, "early_retr": 3 },
            {"thin_dupack": 1, "thin_linear": 1, "early_retr": 3 },
            {"thin_dupack": 1, "thin_linear": 1, "early_retr": 0 },
            {"thin_dupack": 0, "thin_linear": 0, "early_retr": 0 },
        ]
        #p.rdb_option = [False]
        p.payload_values = [400]
        #p.payload_values = [400, 700]
        p.tfrc = [1, 0]
        p.tfrc = [0]
        #defult_conf = {"cong": "cubic"}
        #defult_conf = {"cong": "rdb"}
        defult_conf = {}
        #p.loss_values = ["0.5", "5"]
        #p.loss_values = ["10", "5", "2", "0.5"]
        #p.itt_values = ["100:10", "50:5", "30:3", "10:1", "1"] # "75:7", "50:5",
        p.itt_values = ["1", "5:1", "10:1", "15:1", "25:2", "30:3", "50:5"] # "75:7", "50:5",
        #p.itt_values = ["15:1", "25:2"]
        p.itt_values = ["5:2"]
        p.test_count = [0]

        p.thin_args = dict(defult_conf, name="thin", prefix="r")
        p.packets_in_flight_rdb_limit = [4, 8, 12, 15, 20]
        p.dpif_lim = [10]

        p.packets_in_flight_rdb_limit = [8]
        p.stream_count = 10
        max_streams = max(p.stream_count + 1, 10)
        #thin_range = range(10, max_streams, 5)
        #thin_range = [1, 2, 3, 4, 5, 10, 20]
        #thin_range = [1, 5, 10, 15, 20]
        thin_range = [1]
        thin_stream_count_values =  make_stream(p.thin_args, streams=thin_range)
        thin2_stream_count_values = make_stream(name="thin2", prefix="w", streams=thin_range)
        thick_streams = thin_range
        #thick_streams = [10] * len(thin_stream_count_values)
        print "thin_stream_count_values:", len(thin_stream_count_values)
        #thin2_stream_count_values = make_stream(name="thin2", prefix="y", sr=(p.stream_count, max_streams, 10))
        thick_stream_count_values = make_stream(name="thick", prefix="z", streams=thick_streams)
        #thick_stream_count_values = make_stream(name="thick", prefix="z", streams=range(5, max_streams, 5))
        #print "thick_stream_count_values:", len(thick_stream_count_values)
        #p.streams = zip(thin_stream_count_values, thick_stream_count_values)
        p.streams = zip(thin_stream_count_values, thin2_stream_count_values, thick_stream_count_values)
        return p

    ##############################
    ##############################
    # Simple RDB PIF tests
    ##############################
    def simple_RDB_PIF_tests():
        p = TestProperties(default_test_properties)
        p.job_duration_minutes = [20]
        p.job_duration_minutes = [5]
        p.delay_between_jobs_seconds = 60
        #p.delay_between_jobs_seconds = 1
        p.cong_other = "cubic"
        p.rdb_option = [True, False]
        p.payload_values = [120]
        p.thin_dupack = [1]
        p.thin_linear = [1]
        #p.early_retr = [1]
        #defult_conf = {"cong": "cubic"}
        defult_conf = {"cong": "rdb"}
        #p.loss_values = ["0.5", "5"]
        p.loss_values = ["10", "5", "2", "0.5"]
        p.itt_values = ["100:10", "75:7", "50:5", "30:3"]
        #p.itt_values = ["50"]
        p.thin_args = dict(defult_conf, name="thin", prefix="r")
        p.packets_in_flight_rdb_limit = [4, 8]
        #p.packets_in_flight_rdb_limit = [4]
        p.stream_count = 20
        max_streams = max(p.stream_count + 1, 22)
        thin_stream_count_values =  make_stream(p.thin_args, sr=(p.stream_count, max_streams, 21 + max_streams))
        #thin2_stream_count_values = make_stream(name="thin2", prefix="y", sr=(p.stream_count, max_streams, 10))
        #p.thick_stream_count_values = make_stream(name="thick", prefix="z", sr=(10, 11, 10))
        #p.streams = zip(thin_stream_count_values, thin2_stream_count_values)
        p.streams = [thin_stream_count_values]
        return p

    ##############################
    ##############################
    # Thin stream MOD CDF
    ##############################
    def thin_stream_MOD_CDF():
        p = TestProperties(default_test_properties)
        p.job_duration_minutes = [5]
        p.delay_between_jobs_seconds = 60
        p.cong_other = "cubic"
        p.rdb_option = [False]
        p.payload_values = [120]
        p.thin_dupack = [0, 1]
        p.thin_linear = [0, 1]
        p.early_retr = [0, 3]
        p.thin_dupack = [0]
        p.thin_linear = [0]
        p.early_retr = [3]
        defult_conf = {"cong": "cubic"}
        p.thin_args = dict(defult_conf, name="thin", prefix="r", itt="1")
        p.stream_count = 21
        max_streams = max(p.stream_count + 1, 22)
        print "RANGE:", range(p.stream_count, max_streams, 21 + max_streams)
        thin_stream_count_values =  make_stream(p.thin_args, itt="100", streams=range(p.stream_count, max_streams, 21 + max_streams))
        thick_stream_count_values = make_stream(name="thick", prefix="z", streams=range(10, 11, 10))
        p.streams = zip(thin_stream_count_values, thick_stream_count_values)
        return p

    p = thin_stream_MOD_CDF()
    #p = simple_RDB_PIF_tests()
    #p = RDB_vs_greedy_tests()
    #p = RDB_vs_greedy_misuse_tests()
    #p = TFRC_RDB_vs_greedy_tests()
    #p = module_testing()

    # We want session jobs that are structured something like this:
    """
    {'description': '1 thin rdb stream with fixed loss 1',
     'name_id': '1_thin_rdb_stream-fixed-loss_1',
     'substitutions': {'thin-rdb': {'loss': 'loss 1',
                                    'options': '-r',
                                    'stream': '-I i:30,S:20:5,d:20',
                                    'stream_count': '-c 1',
                                   }
                      },
     'timeout_secs': None
    }
    """
    session_job_index = 1

    session_info_format = "%5s %10s %10s %5s %5s %10s %21s %6s"
    session_jobs_str = session_info_format % ("Duration", "Streams", "ITT", "RTT", "Payload", "Packets in flight Lim", "Options", "Loss")

    def create_job_dict(p):
        #stream_count_thin1 = stream_count_thin
        #stream_count_thin2 = stream_count_thin
        #if type(stream_count_thin) is tuple:
        #    stream_count_thin1, stream_count_thin2 = stream_count_thin

        def make_conf(d, itt, cong_control):
            conf = {}
            conf["stream_count"] = "-c %d" % d.stream_count
            conf["thin-packet-limit"] = "%d" % p_in_flight_limit
            conf["start_port"] = "-P %d" % start_port[d.name]

            itt_base = itt
            if not type(itt) is int:
                itt_base = itt.split(":")[0]

            if d.name == "thick":
                ramp_up_time = int(rtt) / d.stream_count
            else:
                ramp_up_time = int(itt_base) / d.stream_count

            conf["ramp_up_time"] = "-j %d" % ramp_up_time
            conf["stream_duration"] = "-d %dm" % duration
            conf["sack"] = 1
            conf["eretr"] = d.early_retr
            conf["options"] = ""

            if d.name == "thin":
                conf["tfrc"] = tfrc
                conf["rdb"] = 1 if rdb is not False else 0
                conf["dpif"] = dpif_lim
            else:
                conf["tfrc"] = 0
                conf["rdb"] = 0
                conf["dpif"] = 0

            if d.name == "thick":
                conf["stream"] = "-I b:%dKb" % p.bandwidth_rate_cap_kbit
                conf["retrans-collapse"] = "%s" % collapse_thick
            else:
                conf["retrans-collapse"] = "%s" % collapse_thin
                conf["stream"] = "-i %s -S %d" % (itt, payload)
                conf["options"] += " -m" if d.thin_dupack else ""
                conf["options"] += " -a" if d.thin_linear else ""
                conf["options"] += " -G %s" % cong_control
                conf["options"] += " -B%s" % (d.abuser) if d.abuser else ""

                #print "%s options: %s" % (d.name, conf["options"])

            if d.name == "thin":
                conf["options"] += " -r" if rdb is not False else ""

            return conf

        streams_str = ""
        stream_counts = ""
        sj = {'substitutions': {}}

        for d_orig in stream_values:
            d = d_orig.copy()  # Since we modify the content we must copy first

            if d.name in default_options:
                d.update(default_options[d.name])

            d.thin_dupack = d.get("thin_dupack", thin_dupack)
            d.thin_linear = d.get("thin_linear", thin_linear)
            d.early_retr = d.get("early_retr", early_retr)
            d.abuser = d.get("abuser", False)
            cong_control = d.get("cong", cong_thin)
            stream_itt = d.get("itt", itt)

            #if d.name == "thin2":
            #    cong_control = "cubic"
            #    d.cong  = "cubic"

            sj["substitutions"][d.name] = make_conf(d, stream_itt, cong_control)
            s_str = "%s%d" % (d.prefix, d.stream_count)
            stream_counts += " %d" % d.stream_count

            if d.name == "thin":
                s_str += "-%s-itt%s-ps%d-cc%s-da%d-lt%d-er%d" % ("rdb" if rdb is not False else "tcp", stream_itt, payload, cong_control, d.thin_dupack, d.thin_linear, d.early_retr)

            if d.name == "thin":
                if rdb is True:
                    s_str += "-pif%d" % p_in_flight_limit
                elif rdb is "dpif":
                    s_str += "-dpif%d" % dpif_lim
                if not tfrc is None:
                    s_str += "-tfrc%d" % tfrc
            elif d.name != "thick":
                s_str += "-%s-itt%s-ps%d-cc%s" % ("tcp", stream_itt, payload, cong_control)

            if d.abuser:
                s_str += "-ab%s" % d.abuser

            if d.name != "thick":
                if collapse_thin:
                    s_str += "-rc%d" % (collapse_thin)

            if streams_str:
                streams_str += " vs "
            streams_str += s_str

        sj["substitutions"]["segmentation-offload"] = { "segmentation-offload" : segm_off }

        bandwidth_delay_product_bytes_ps = ((p.bandwidth_rate_cap_kbit * 1000) * (rtt / 2 * (10**-3))) / 8
        queue_limit = int(bandwidth_delay_product_bytes_ps)
        queue_limit *= 2

        if queue_type == "pfifo":
            queue_limit = int(math.ceil(queue_limit / 1500.0))

        if queue_lim:
            queue_limit = queue_lim

        delay_type = "fixed"
        #queue_limit = 10
        #print "queue_limit:", queue_limit

        sj["substitutions"]["netem-data-path"] = { "delay": "delay %dms" % (rtt // 2), "loss": "" }
        sj["substitutions"]["netem-ack-path"] = { "delay": "delay %dms" % (rtt // 2), "loss": "" }

        sj["substitutions"]["rate"] = { "bandwidth_rate_cap": "%dkbit" % p.bandwidth_rate_cap_kbit,
                                        "queue_limit": str(queue_limit),
                                        "queue_type": queue_type }
        sj["substitutions"]["rate"].update({ "bridge_interface_speed": bridge_interface_speed })

        if loss:
            sj["substitutions"]["netem-data-path"].update({"loss": "loss %s%%" % loss})

        #print "queue_limit:", queue_limit

        def make_for_each(substitution_name, each, status="", prefix=""):
            foreach_ids = []
            foreach_values = {}
            for e in each:
                if type(status) is dict:
                    val = status["default"]
                    if e in status:
                        val = status[e]
                    foreach_ids.append("%s%s%s" % (prefix, e, "-" + val if val else val))
                    foreach_values[foreach_ids[-1]] = { substitution_name: ("%s %s" % (e, val)).strip() }
                else:
                    foreach_ids.append("%s%s%s" % (prefix, e, "-" + status if status else status))
                    foreach_values[foreach_ids[-1]] = { substitution_name: ("%s %s" % (e, status)).strip() }
            return foreach_ids, foreach_values

        ids, values = make_for_each("segmentation-offload", segmentation_types, segm_off)
        sj["substitutions"]["all-segmentation-offload"] = { "foreach": ids }
        sj["substitutions"].update(values)

        ids, values = make_for_each("segmentation-offload", segmentation_types, segm_off_thin, prefix="thin-")
        sj["substitutions"]["thin-segmentation-offload"] = { "foreach": ids }
        sj["substitutions"].update(values)

        ids, values = make_for_each("segmentation-offload", segmentation_types, segm_off_thick, prefix="thick-")
        sj["substitutions"]["thick-segmentation-offload"] = { "foreach": ids }
        sj["substitutions"].update(values)

        hosts = ["zsender", "rdbsender", "bridge2", "bridge3", "zreceiver"]
        ids, values = make_for_each("hostname", hosts, prefix="sysctl-ethtool-")
        sj["substitutions"]["sysctl_ethtool_output"] = { "foreach": ids }
        sj["substitutions"].update(values)

        #delay_type = "variable"
        #foreach_list = []
        #for i in range(stream_count):
        #    foreach_list.append("netem_subst_id_" + str(i))
        #sj["substitutions"]["netem_delay"] = { "foreach": foreach_list }
        #
        #for i in range(stream_count):
        #    stream_index = 0
        #    sj["substitutions"][foreach_list[i]] = { "band": i, "delay": "delay %dms" % ((rtt // 2.3) + (stream_index * 4)),
        #                                                                              "source_port": start_port_thick + stream_index, "dest_port": 5001,
        #                                                                              "handle": "%d%d" % (1, stream_index), "classid": "%d" % (10 + stream_index) }

        loss_type = "fixed" if loss.startswith("fixed") else "%s" % loss

        sj["duration"] = duration
        sj["description"] = "%s cap: %dkbit stream %dmin"\
            "rtt: %d, loss %s, p_in_flight: %d, Queue Length: %d, Test num: %d" % (streams_str, p.bandwidth_rate_cap_kbit, duration,
                                                                                   rtt, loss_type, p_in_flight_limit, queue_limit, test_num)
        sj["name_id"] = "%s..kbit%d_min%d"\
                        "_rtt%d_loss%s_pif%d_qlen%d_delay%s_num%d" % (streams_str.replace(" ", "_"),
                                                                      p.bandwidth_rate_cap_kbit,
                                                                      duration, rtt, loss_type,
                                                                      p_in_flight_limit, queue_limit, delay_type, test_num)
        #if collapse_thin:
        #    sj["name_id"] += "_clps-t-%s" % collapse_thin
        #if collapse_thick:
        #    sj["name_id"] += "_clps-g-%s" % collapse_thick
        if not segm_off == "off":
            sj["name_id"] += "_soff-%s" % (1 if segm_off is "on" else 0)
        if not segm_off_thin == "off":
            if type(segm_off_thin) is dict:
                sj["name_id"] += "_soff-t-%s" % (1 if segm_off_thin["default"] is "on" else 0)
                for k in segmentation_types:
                    if not k in segm_off_thin:
                        continue
                    sj["name_id"] += "_%s-t-%s" % (k, (1 if segm_off_thin[k] is "on" else 0))
            else:
                sj["name_id"] += "_soff-t-%s" % (1 if segm_off_thin is "on" else 0)
        if not segm_off_thick == "off":
            sj["name_id"] += "_soff-g-%s" % (1 if segm_off_thick is "on" else 0)

        if bridge_interface_speed:
            sj["name_id"] += "_brate-%s" % bridge_interface_speed.replace(" ", "-").replace("speed_", "")

        job_str = session_info_format % (duration, stream_counts.strip(), itt, rtt, payload, p_in_flight_limit, sj["substitutions"]["thin"]["options"], loss)
        return job_str, sj

    session_job_list = []
    jobs_dup_dict = {}

    # Loop over the product of all the values in the value lists
    for (loss, rdb, stream_values, itt, rtt, payload, duration,
         segm_off, segm_off_thin, segm_off_thick, collapse_thin, collapse_thick,
         bridge_interface_speed, ramp_up_time,
         queue_type, cong_thin, thin_dupack, thin_linear, early_retr, queue_lim, test_num) in itertools.product(p.loss_values, p.rdb_option,
                                                                                                                p.streams, p.itt_values,
                                                                                                                p.rtt_values, p.payload_values,
                                                                                                                p.job_duration_minutes, p.segmentation_offload,
                                                                                                                p.segmentation_offload_thin, p.segmentation_offload_thick,
                                                                                                                p.retrans_collapse_thin, p.retrans_collapse_thick,
                                                                                                                p.bridge_interface_speeds, p.ramp_up_times, p.queue_types, p.cong_thin,
                                                                                                                p.thin_dupack, p.thin_linear, p.early_retr, p.queue_limit, p.test_count):
        #stream_count_thin, stream_count_thick = stream_counts
        #print "stream_values:", stream_values
        custom_session_settings["default_session_job_timeout_secs"] = duration * 60
        #segmentation_offload="off", segmentation_offload_thin="off", segmentation_offload_thick="off",
        # Use same for all hosts
        #segm_off_thin = segm_off
        #segm_off_thick = segm_off
        p_in_flight_limit = 0
        dpif_lim = 0
        default_options = None
        tfrc = 0

        if rdb is True:
            default_options = deepcopy(p.default_options)
            default_options["thin"]["cong"] = "rdb"
            for p_in_flight_limit, tfrc in itertools.product(p.packets_in_flight_rdb_limit, p.tfrc):
                job_str, sj = create_job_dict(p)
                if sj["name_id"] in jobs_dup_dict:
                    print "A job with this key already exists:", sj["name_id"]
                else:
                    session_job_list.append(sj)
                    session_jobs_str += job_str
                    jobs_dup_dict[sj["name_id"]] = None
        # Dynamic pif
        elif rdb is "dpif":
            default_options = deepcopy(p.default_options)
            default_options["thin"]["cong"] = "rdb"
            for dpif_lim, tfrc in itertools.product(p.dpif_lim, p.tfrc):
                job_str, sj = create_job_dict(p)
                if sj["name_id"] in jobs_dup_dict:
                    print "A job with this key already exists:", sj["name_id"]
                else:
                    session_job_list.append(sj)
                    session_jobs_str += job_str
                    jobs_dup_dict[sj["name_id"]] = None
        else:
            if not p.tcp_args_options:
                p.tcp_args_options = [None]

            for options in p.tcp_args_options:
                default_options = deepcopy(p.get("default_options", {}))
                #print "options:", options
                if options is not None:
                    for k in options:
                        #print "Key:", k
                        default_options[k].update(options[k])
                #print "default_options:", default_options

                #cong_thin = p.cong_other
                job_str, sj = create_job_dict(p)
                if sj["name_id"] in jobs_dup_dict:
                    print "A job with this key already exists:", sj["name_id"]
                else:
                    session_job_list.append(sj)
                    session_jobs_str += job_str
                    jobs_dup_dict[sj["name_id"]] = None

    #start_port_thick += stream_count * 2
    #start_port_thin += stream_count * 2

    for i, sj in enumerate(session_job_list):
        sj["job_index"] = [i + 1, len(session_job_list)]

    import StringIO
    job_list_output = StringIO.StringIO()
    pp = pprint.PrettyPrinter(indent=1, width=100, depth=None, stream=job_list_output)

    print "session_job_list:", len(session_job_list)
    custom_session_settings["session_jobs"] = list(session_job_list)
    custom_session_settings["delay_between_session_jobs_secs"] = p.delay_between_jobs_seconds
    #print "custom_session_settings:", custom_session_settings["session_jobs"][0]["substitutions"]["thin"].keys()

    try:
        settings, session_jobs, jobs, cleanup_jobs, scp_jobs = scheduler.setup(args, custom_session_settings=custom_session_settings, custom_settings=custom_settings)
    except Exception, e:
        print "Error:", e
        import traceback
        traceback.print_exc()
        print "Custom session settings:"
        pp_std = pprint.PrettyPrinter(indent=1, width=100)
        #pp_std.pprint(custom_session_settings)
        return

    skipped = 0
    if args.name and args.resume:
        i = 0
        while i < len(session_jobs["session_jobs"]):
            sj = session_jobs["session_jobs"][i]
            #print "JOB:", sj
            for scp in scp_jobs:
                fname = "%s/%s_%s" % (scheduler.settings["resume_results_dir"], sj["name_id"], scp[0]["target_filename"])
                #print "File:", fname
                if os.path.isfile(fname):
                    print "Found results file for job '%s' (%s)" % (sj["name_id"], fname)
                    print "Skipping job"
                    del session_jobs["session_jobs"][i]
                    i -= 1
                    skipped += 1
                    break
            i += 1

    # Find the estimated time
    estimated_total_duration = 0
    for i, sj in enumerate(session_jobs["session_jobs"]):
        estimated_total_duration += sj["duration"]

    # Find the estimated time including skipped jobs
    estimated_total_duration_all = 0
    for i, sj in enumerate(session_job_list):
        estimated_total_duration_all += sj["duration"]

    # Add the delay between the jobs
    if len(session_jobs["session_jobs"]) > 1:
        estimated_total_duration += (len(session_jobs["session_jobs"]) - 1) * (p.delay_between_jobs_seconds/60.0 + 2)
    estimated_total_duration_all += (len(session_job_list) - 1) * (p.delay_between_jobs_seconds/60.0 + 2)

    def print_job_duration_estimations():
        print "Estimated total duration of all jobs(%d): %dh %dm" % (len(session_job_list), estimated_total_duration_all / 60, estimated_total_duration_all % 60)
        print "Estimated total duration of jobs to run (%d): %dh %dm" % (len(session_jobs["session_jobs"]), estimated_total_duration / 60, estimated_total_duration % 60)

    print_job_duration_estimations()

    if args.print_job_names:
        #pp_std = pprint.PrettyPrinter(indent=1, width=100)
        #pp_std.pprint(session_job_list)
        #print "Job count: %d (Skipped: %d)" % (len(session_job_list), skipped)
        print "Job count: %d (" % len(session_job_list),
        cprint("Skipped: %d" % skipped, "yellow", end="")
        print "):"
        for sj in session_job_list:
            found = False
            for scp in scp_jobs:
                fname = "%s/%s_%s" % (scheduler.settings["resume_results_dir"], sj["name_id"], scp[0]["target_filename"])
                if args.resume and os.path.isfile(fname):
                    found = True
                    break
            if found:
                cprint("   %s" % sj["name_id"], "yellow")
            else:
                print "  ", sj["name_id"]

        print_job_duration_estimations()
        scheduler.lockFileHandler.stop()
        sys.exit(0)

    if args.print_dictionary:
        pp_std = pprint.PrettyPrinter(indent=1, width=100)
        pp_std.pprint(session_job_list)
        print "Job count:", len(session_job_list)
        if skipped:
            print "Jobs skipped:", skipped
        print "Estimated total duration: %dh %dm" % (estimated_total_duration / 60, estimated_total_duration % 60)
        print "Estimated total duration of all jobs: %dh %dm" % (estimated_total_duration_all / 60, estimated_total_duration_all % 60)
        scheduler.lockFileHandler.stop()
        sys.exit(0)

    session_jobs_info = "Jobs to run %d\n\n" % len(session_job_list)
    session_jobs_info += "Session jobs dict:\n%s" % job_list_output.getvalue()
    session_jobs_info += session_jobs_str
    job_list_output.close()

    if abort:
        return

    scheduler.do_run_jobs(settings, session_jobs, jobs, cleanup_jobs, scp_jobs, args, session_info_to_file=session_jobs_info)

if __name__ == "__main__":
    main()
