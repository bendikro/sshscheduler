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

estimated_total_duration = 0

def main():
    import scheduler
    global estimated_total_duration

    argparser = argparse.ArgumentParser(description="Run test sessions")
    argparser.add_argument("-p", "--print-dictionary",  help="Print the session dictionary and exit instead of running the jobs.", action='store_true', required=False)
    args = scheduler.parse_args(argparser)

    custom_session_settings = {}
    test_count = [0,1,2,3,4]
    test_count = [0]

    bandwidth_rate_cap_kbit = 2000
    #delay_between_jobs_seconds = 400
    delay_between_jobs_seconds = 2
    #job_duration_minutes = [30, 60, 120]
    #job_duration_minutes = [10, 20]
    #job_duration_minutes = [10, 15, 20, 30]
    job_duration_minutes = [20]
    #job_duration_minutes = [10]
    #job_duration_minutes = [45, 60]
    job_duration_minutes = [1]

    # Create session jobs from all variations of the following options:
    loss_values = [""]
    rdb_option = [False, True]
    payload_values = [100]
    #stream_count_values = [1, 32, 128, 512]
    #stream_count_values = [50, 64, 90]
    stream_count_values = [16]
    #stream_count_values = [100, 500]

    #loss_values = ["0.5", "5", "fixedv 7,8,9,11,15,16,17,18,19,20,30 40"]
    #itt_values = [50, 100]
    #rtt_values = [30, 100, 200]

    #rtt_values = [100, 200]
    packets_in_flight_rdb_limit = [3, 6, 10, 20]
    #packets_in_flight_rdb_limit = [3]

    itt_values = [100]
    rtt_values = [100]

    start_port_thick = 12000
    start_port_thin =  22000

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

    def create_job_dict(loss="", rdb=None, stream_count=None, duration=None, itt=None, rtt=None, payload=None, p_in_flight_limit=None, num=None):
        #global estimated_total_duration
        #estimated_total_duration += duration

        sj = {'substitutions': {} }
        sj['substitutions']["thin"] = {}
        sj["substitutions"]["thin"]["options"] = "-r" if rdb else ""
        sj["substitutions"]["thin"]["stream"] = "-I i:%d,S:%d" % (itt, payload)
        sj["substitutions"]["thin"]["stream_count"] = "-c %d" % stream_count
        sj["substitutions"]["thin"]["thin-packet-limit"] = "%d" % p_in_flight_limit
        sj["substitutions"]["thin"]["stream_duration"] = "-d %dm" % duration
        sj["substitutions"]["thin"]["start_port"] = "-P %d" % start_port_thin

        sj["substitutions"]["thick"] = {}
        sj["substitutions"]["thick"]["stream"] = "-I b:%dKb" % bandwidth_rate_cap_kbit
        sj["substitutions"]["thick"]["stream_count"] = "-c %d" % stream_count
        sj["substitutions"]["thick"]["stream_duration"] = "-d %dm" % duration
        sj["substitutions"]["thick"]["start_port"] = "-P %d" % start_port_thick

        bandwidth_delay_product_bytes_ps = ((bandwidth_rate_cap_kbit * 1000) * (rtt * 10**-3)) / 8
        queue_limit = int(math.ceil(bandwidth_delay_product_bytes_ps / 1540))

        sj["substitutions"]["netem"] = { "delay": "delay %dms" % (rtt // 2), "loss": "" }
        sj["substitutions"]["rate"] = { "bandwidth_rate_cap": "%dkbit" % bandwidth_rate_cap_kbit, "queue_packet_length": str(queue_limit) }

        stream_type = "rdb" if rdb else "tcp"
        loss_type = "fixed" if loss.startswith("fixed") else "%s" % loss
        sj["duration"] = duration
        sj["description"] = "%d thin %s vs %d thick cap: %dkbit stream %dmin with payload %d, itt %d rtt: %d, loss %s, p_in_flight: %d, Test num: %d" % (stream_count, stream_type, stream_count,
                                                                                                                                                         bandwidth_rate_cap_kbit, duration,
                                                                                                                                                         payload, itt,
                                                                                                                                                         rtt, loss_type, p_in_flight_limit, num)
        sj["name_id"] =     "%d_thin_%s_vs_%d_thick_stream_cap_%dkbit_duration_%dm_payload_%d_itt_%d_rtt_%d_loss_%s_p_in_flight_%d_num_%d"  % (stream_count, stream_type, stream_count,
                                                                                                                                               bandwidth_rate_cap_kbit,
                                                                                                                                               duration, payload, itt, rtt, loss_type,
                                                                                                                                               p_in_flight_limit, num)
        job_str = session_info_format % (duration, stream_count, itt, rtt, payload, p_in_flight_limit, sj["substitutions"]["thin"]["options"], loss)
        return job_str, sj

    session_job_list = []
    # Loop over the product of all the values in the value lists
    for loss, rdb, stream_count, itt, rtt, payload, duration, test_num in itertools.product(loss_values, rdb_option,
                                                                        stream_count_values, itt_values,
                                                                        rtt_values, payload_values,
                                                                        job_duration_minutes, test_count):
        custom_session_settings["default_session_job_timeout_secs"] = duration * 60

        if rdb:
            for p_in_flight_limit, e in itertools.product(packets_in_flight_rdb_limit, [1]):
                job_str, sj = create_job_dict(rdb=rdb, stream_count=stream_count, duration=duration, itt=itt, rtt=rtt, payload=payload, p_in_flight_limit=p_in_flight_limit, num=test_num)
                session_job_list.append(sj)
                session_jobs_str += job_str
        else:
            job_str, sj = create_job_dict(rdb=rdb, stream_count=stream_count, duration=duration, itt=itt, rtt=rtt, payload=payload, p_in_flight_limit=0, num=test_num)
            session_job_list.append(sj)
            session_jobs_str += job_str

    #start_port_thick += stream_count * 2
    #start_port_thin += stream_count * 2

    for i, sj in enumerate(session_job_list):
        sj["job_index"] = [i + 1, len(session_job_list)]

    import StringIO
    job_list_output = StringIO.StringIO()
    pp = pprint.PrettyPrinter(indent=1, width=100, depth=None, stream=job_list_output)

    custom_session_settings["session_jobs"] = session_job_list
    custom_session_settings["delay_between_session_jobs_secs"] = delay_between_jobs_seconds

    settings, session_jobs, jobs, cleanup_jobs, scp_jobs = scheduler.setup(args, custom_session_settings=custom_session_settings)

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
    for i, sj in enumerate(session_job_list):
        estimated_total_duration += sj["duration"]

    estimated_total_duration += (len(session_job_list) - 1) * (delay_between_jobs_seconds/60)
    print "Estimated total duration of all jobs: %dh %dm" % (estimated_total_duration / 60, estimated_total_duration % 60)

    if args.print_dictionary:
        pp_std = pprint.PrettyPrinter(indent=1, width=100)
        pp_std.pprint(session_job_list)
        print "Job count:", len(session_job_list)
        if skipped:
            print "Jobs skipped:", skipped
        print "Estimated total duration of all jobs: %dh %dm" % (estimated_total_duration / 60, estimated_total_duration % 60)
        scheduler.lockFileHandler.stop()
        sys.exit(0)

    session_jobs_info = "Jobs to run %d\n\n" % len(session_job_list)
    session_jobs_info += "Session jobs dict:\n%s" % job_list_output.getvalue()
    session_jobs_info += session_jobs_str
    job_list_output.close()

    scheduler.do_run_jobs(settings, session_jobs, jobs, cleanup_jobs, scp_jobs, args, session_info_to_file=session_jobs_info)

if __name__ == "__main__":
    main()
