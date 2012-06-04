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

from threading import Thread

def print_t(*arg):
    import thread, threading
    print("%s: " % threading.current_thread().name, end="")
    print(*arg)

class Job(Thread):

    def __init__(self, host_conf, commands):
        Thread.__init__(self)
        self.host = host_conf["host"]
        self.commands = commands
        self.timeout = 30 # Default timeout of 30 seconds

        self.logfile = None
        if host_conf.has_key("logfile"):
            self.logfile = host_conf["logfile"]

        if host_conf.has_key("timeout"):
            self.timeout = host_conf["timeout"]

    def run(self):
        child = self.ssh_login("root", self.host)
    
        if not child:
            print_t("Failed connect to host %s" % self.host)
            return
        result = self.execute_commands(child, self.commands)
        
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
                    child.expect(c["expect"])                    
                    print_t("Expecting:", c["expect"])
                else:
                    child.expect(PEXPECT_COMMAND_PROMPT)
                # Makes the call return
            except Exception, e:
                print_t("Exception!", str(e))

            # Print terminal prints
            #print_t("Job output:\n%s\n" % child.before)
            print_t("Job output:\n%s\n" % child.after)
            
            if c.has_key("kill") and c["kill"] is True:
                print_t("Killing command ", command)
                child.kill(15)

        print_t("Jobs on host %s are done. exiting host" % self.host)

        # Now exit the remote host.
        child.sendline('exit')
        index = child.expect([pexpect.EOF, "(?i)there are stopped jobs"])
        if index == 1:
            child.sendline("exit")
            child.expect(EOF)
            
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
        child = pexpect.spawn(ssh, timeout=self.timeout)
        
        if self.logfile:
            fout = file(self.logfile, "w")
            child.logfile = fout
            print_t("Using logfile:", self.logfile)

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


def parse_jobs(filename):
    jobs = []
    job = None
    f = open(filename, 'r')
    for line in f.readlines():
        line = line.strip()

        if line.startswith("#"):
            continue

        # Job definition over
        if line == "":
            if job == None:
                continue
            jobs.append(job)
            job = None
        else:
            if job is None:
                job = [eval(line), []]
            else:
                dict_cmd = eval(line)
                job[1].append(dict_cmd)
    # If file doesn't end with empty line
    if job is not None:
        jobs.append(job)
    return jobs

def exit_with_usage():
    print(globals()['__doc__'])
    os._exit(1)

if __name__ == "__main__":

    if len(sys.argv) == 1:
        print("Too few arguments!\n")
        exit_with_usage()

    jobs = parse_jobs(sys.argv[1])

    threads = []    
    from datetime import datetime

    start_time = datetime.now()
    print_t("Starting jobs at ", str(start_time))
    
    for job in jobs:
        t = Job(job[0], job[1])
        threads.append(t)
        t.start()

    for t in threads:
        t.join()
        print_t("Joined thread ", t.name)

    end_time = datetime.now()
    print_t("Job finished at ", str(end_time))
    print_t("Execution time:", str((end_time - start_time)))

    # Gather results


