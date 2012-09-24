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

# Leaves 'print "string"' format absolete
from __future__ import print_function

"""This program runs a sequence of commands on remote hosts using SSH.

./scheduler.py file
    file : A file containing the jobs to schedule.
"""

import os, sys, time, re, getopt, getpass
import traceback
import pexpect

DEFAULT_COMMAND_PROMPT = '[#$] ' ### This is way too simple for industrial use -- we will change is ASAP.
PEXPECT_COMMAND_PROMPT = "\[PEXPECT\]#"

TERMINAL_PROMPT = '(?i)terminal type\?'
TERMINAL_TYPE = 'vt100'
# This is the prompt we get if SSH does not have the remote host's public key stored in the cache.
SSH_NEWKEY = '(?i)are you sure you want to continue connecting'

lock_file = "%s/sshscheduler.lock" % os.getenv("HOME")

from threading import Thread
import thread, threading

print_lock = threading.Lock()

def print_t(*arg):
    print_lock.acquire() # will block if lock is already held
    arg = list(arg)

    # Handles newlines and beginning and end of format string so it looks better with the Thread name printed
    newline_count = 0
    if len(arg) > 0:
        # Removing leading newlines
        while arg[0][0] == "\n":
            print()
            arg[0] = arg[0][1:]
            if arg[0] is "":
                break
        # Count newlines at the end, and remove them
        while arg[0][-1] == "\n":
            newline_count += 1
            arg[0] = arg[0][:-1]

    if not (len(arg) == 1 and len(arg[0]) == 0):
        print("%10s: " % threading.current_thread().name, end="")
        print(*arg)
    if newline_count:
        print("\n" * newline_count)
    print_lock.release()

class Job(Thread):

    def __init__(self, host_conf, commands):
        Thread.__init__(self)
        self.conf = host_conf
        self.host = host_conf["host"]
        self.commands = commands
        self.timeout = 30 # Default timeout of 30 seconds
        self.login_timeout = 10

        self.logfile = None
        if host_conf.has_key("logfile"):
            self.logfile = host_conf["logfile"]

        if host_conf.has_key("timeout"):
            self.timeout = host_conf["timeout"]

    def kill(self):
        if hasattr(self, 'child'):        
            self.child.kill(15)

    def run(self):
        self.name = threading.current_thread().name
        
        if self.conf["type"] == "ssh":
            self.child = self.ssh_login("root", self.host)
            if not self.child:
                print_t("Failed connect to host %s" % self.host)
                return
            result = self.execute_commands(self.child, self.commands)
        elif self.conf["type"] == "scp":
            scp_cmd = "scp %s:%s %s/%s" % (self.host, self.conf["filename"], self.conf["target_dir"], self.conf["target_filename"])
            print_t("Executing scp command: %s" % scp_cmd)
            result = pexpect.run(scp_cmd, withexitstatus=True)
            print_t("Result:", result)
            # Delete file
            #del_cmd = "ssh %s \"rm %s\"" % (self.host, self.conf["filename"])
            #print_t("Deleting pcap file:", del_cmd)
            #pexpect.run(del_cmd)
        
    def execute_commands(self, child, commands):
        for c in commands:
            command = "/bin/bash -c '%s'" % c["command"]
            #print "Executing on %s: %s" % (self.host, command)
            print_t("Executing on %s: %s" % (self.host, command))
            try:
                child.sendline(command)
                
                #timeout = -1
                #if c.has_key("timeout"):
                #    timeout = c["timeout"]

                if c.has_key("expect"):
                    print_t("Expecting string '%s' on host %s" % (c["expect"], self.host))
                    child.expect(c["expect"])                    
                else:
                    return
                #elif not c.has_key("kill"):
                #    print_t("Expecting:", PEXPECT_COMMAND_PROMPT)
                #    child.expect(PEXPECT_COMMAND_PROMPT)
                # Makes the call return
            except Exception, e:
                print_t("Exception==========\n%s\n===========" % str(e))
                pass
            # Print terminal prints
            print_t("\nJob output on '%s': '%s'" % (self.host, child.after))

        print_t("Jobs on host %s has finished. Exiting host" % self.host)

        # Now exit the remote host.
        child.sendline('exit')
        index = child.expect([pexpect.EOF, "(?i)there are stopped jobs", ""])
        if index == 1:
            child.sendline("exit")
            child.expect(pexpect.EOF)

    def ssh_login(self, user, host):
        #
        # Login via SSH
        #
        global DEFAULT_COMMAND_PROMPT, PEXPECT_COMMAND_PROMPT, TERMINAL_PROMPT, TERMINAL_TYPE, SSH_NEWKEY
    
        import os, re
        has_user = re.match(".+@.+", host)
        if not has_user and user:
            host = "%s@%s" % (os.getenv('USER'), host)

        print_t("Connecting to host '%s' with timeout '%s'" % (host, str(self.timeout)))
        
        ssh = "ssh %s" % (host)
        #print_t("cmd:" + ssh)
        child = pexpect.spawn(ssh, timeout=self.timeout, maxread=100, searchwindowsize=100)
        
        if self.logfile:
            fout = file(os.path.join(self.conf["log_dir"] , self.logfile), "w")
            child.logfile = fout
            #print_t("Using logfile:", self.logfile)

        i = child.expect([pexpect.TIMEOUT, SSH_NEWKEY, DEFAULT_COMMAND_PROMPT, '(?i)password'])
        
        #print "Greeting:", child.before
        if i == 0: # Timeout
            print_t('ERROR! could not login with SSH. Here is what SSH said:')
            print_t(child.before, child.after)
            sys.exit (1)
        if i == 1: # In this case SSH does not have the public key cached.
            child.sendline ('yes')
            child.expect ('(?i)password')
        if i == 2:
            # This may happen if a public key was setup to automatically login.
            # But beware, the DEFAULT_COMMAND_PROMPT at this point is very trivial and
            # could be fooled by some output in the MOTD or login message.
            pass
        if i == 3:
            print_t("The machine is asking for a password. You should set up ssh keys to avoid this!")
            sys.exit()
            #child.sendline(password)
            # Now we are either at the command prompt or
            # the login process is asking for our terminal type.
            i = child.expect ([DEFAULT_COMMAND_PROMPT, TERMINAL_PROMPT])
            if i == 1:
                child.sendline (TERMINAL_TYPE)
                child.expect (DEFAULT_COMMAND_PROMPT)
        #
        # Set command prompt to something more unique.
        #
        #child.sendline ('PS1="[PEXPECT]# "') # In case of sh-style
        #child.sendline ("set prompt='[PEXPECT]# '")
        child.sendline ("PS1='[PEXPECT]# '")
        
        i = child.expect([pexpect.TIMEOUT, PEXPECT_COMMAND_PROMPT], timeout=10)
        #print_t("RETURNED1:", child.before)
        if i == 0:
            print_t("# Couldn't set sh-style prompt -- trying csh-style.")
            child.sendline ("set prompt='[PEXPECT]# '")
            i = child.expect ([pexpect.TIMEOUT, PEXPECT_COMMAND_PROMPT], timeout=10)
            if i == 0:
                print_t("Failed to set command prompt using sh or csh style.")
                print_t("Response was:")
                print_t(child.before)
                sys.exit (1)
        # Success
        return child


settings = None

def parse_jobs(filename):
    global settings
    jobs = []
    job = None
    f = open(filename, 'r')
    for line in f.readlines():
        line = line.strip()

        if line.startswith("#") or line.strip() == "":
            continue
        try:
            d = eval(line)
        except:
            print("Failed to parse line:", line)
            print("Each line must be a valid python dictionary")
            sys.exit()

        # New host
        if d.has_key("host"):
            if job is not None:
                jobs.append(job)
            job = [d, []]
        # Command for host
        elif d.has_key("command"):
            job[1].append(d)
        # Do a sleep or wait for all previous jobs
        elif d.has_key("sleep") or d.has_key("wait") or d.has_key("cleanup"):
            if job is not None:
                jobs.append(job)
            jobs.append([d])
            job = None
        elif d.has_key("settings"):
            settings = d

    # Add last job
    if job is not None:
        jobs.append(job)
    return jobs

def exit_with_usage():
    print(globals()['__doc__'])
    os._exit(1)

threads = []    
threads_to_kill = []


def abort_job():
    print_t("Jobs to kill:", (len(threads) + len(threads_to_kill)))
    kill_threads(threads)
    kill_threads(threads_to_kill)

def kill_threads(threads_list):
    for t in threads_list:
        try:
            print_t("read_nonblocking: %s : %s" % (t.host, str(t.commands)))
            if hasattr(t, 'child'):
                t.child.read_nonblocking(size=1000, timeout=0)
        except (pexpect.TIMEOUT, pexpect.EOF) as e:
            #print_t("Exception: %s : %s" % (type(e), e))
            # pexpect.TIMEOUT raised if no new data in buffer
            # pexpect.EOF raised when it reads EOF
            pass
        print_t("Killing command %s : %s" % (t.host, str(t.commands)))
        t.kill()


from datetime import datetime
from time import sleep

def join_current_threads():
    global threads
    #print_t("Joining threads")
    for t in threads:
        while t.isAlive():
            try:
                t.join(1)
            except KeyboardInterrupt, e:
                #print("Exception", str(e))
                #print_t("SIGTERM Received")
                return False
    threads = []
    return True

def handle_only_one_job_in_execution():
    if os.path.isfile(lock_file):
        f = open(lock_file, 'r')
        content = f.read()
        f.close()
        return content
    f = open(lock_file, 'w+')
    date = datetime.now().strftime("%Y-%m-%d-%H%M-%S")
    f.write("Test name: %s\n" % settings["test_name"])
    f.write("Started at: %s\n" % date)
    f.close()
    return None

def setup_log_directories():
    # Setup directories for storing pcap and log files
    job_date = datetime.now().strftime("%Y-%m-%d-%H%M-%S")
    jobname_dir = "%s/%s" % (settings["pcap_dir"], settings["test_name"])
    pcap_dir = "%s/%s" % (jobname_dir, job_date)
    log_dir = "%s/logs" % pcap_dir
    last_dir = "%s/last" % jobname_dir
    os.makedirs(log_dir)
    try:
        os.makedirs(last_dir)
    except:
        pass
    return pcap_dir, log_dir, last_dir


if __name__ == "__main__":

    if len(sys.argv) == 1:
        print("Too few arguments!\n")
        exit_with_usage()

    jobs = parse_jobs(sys.argv[1])

    if handle_only_one_job_in_execution() is not None:
        print("Lock file is present (%s). Either a job is currently running, "
              "or a the lock file from a previous job was not correctly removed." % lock_file)
        f = open(lock_file, "r")
        print("Lock file content:", f.read())
        f.close()
        sys.exit()

    pcap_dir, log_dir, last_dir = setup_log_directories()

    start_time = datetime.now()
    print("\nStarting test '%s' at %s" % (settings["test_name"], str(start_time)))

    current_index = 0
    for i in range(len(jobs)):
        current_index = i
        job = jobs[i]
        if job[0].has_key("host"):
            job[0]["log_dir"] = log_dir
            if not job[0].has_key("timeout"):
                job[0]["timeout"] = settings["default_timeout"]
            t = Job(job[0], job[1])
            if job[0].has_key("kill") and job[0]["kill"] is True:
                threads_to_kill.append(t)
            else:
                threads.append(t)
            t.start()
        elif job[0].has_key("sleep"):
            sleep(float(job[0]["sleep"]))
        elif job[0].has_key("wait"):
            print_t("\nWAIT - waiting for threads")
            # Wait for all previous jobs before continuing
            if join_current_threads():
                # Job was not aborted by SIGTERM. Kill the jobs denoted with kill
                print_t("Jobs completed uninterupted. Killing threads:", len(threads_to_kill))
                kill_threads(threads_to_kill)
                break
            else:
                print_t("\nTest interrupted by CTRL-c!\n")
                abort_job()
                break
               
    end_time = datetime.now()

    # Gather results
    print_t("\nTEST HAS FINISHED - GATHERING RESULTS")
    print_t("Saving pcap files to:", pcap_dir)

    threads = []
    for i in range(current_index + 1, len(jobs)):
        job = jobs[i]
        job[0]["target_dir"] = pcap_dir
        t = Job(job[0], None)
        threads.append(t)
        t.start()

    join_current_threads()
    
    # Copy results to last directory
    cmd = "rm -f %s/*.pcap && rm -f %s/logs/* && cp -R %s/* %s/" % (last_dir, last_dir, pcap_dir, last_dir)
    out = os.popen(cmd).read()

    print_t("\nExecution of '%s' finished at %s" % (settings["test_name"], str(end_time)))
    print_t("Test executed in ", str((end_time - start_time)))
    
    os.remove(lock_file)
 
