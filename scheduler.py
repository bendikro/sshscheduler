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

"""
This program runs a sequence of commands on remote hosts using SSH.
"""

import os, sys, time, re, argparse, thread, threading, traceback, select
import pexpect
from pxssh import pxssh
import signal
from datetime import datetime
from threading import Thread
import copy

try:
    from termcolor import colored, cprint
    termcolor = True
except:
    print("termcolor could not be found. To enable colors in terminal output, install termcolor.")
    termcolor = False

DEFAULT_COMMAND_PROMPT = '[#$] ' ### This is way too simple for industrial use -- we will change is ASAP.
PEXPECT_COMMAND_PROMPT = "\[PEXPECT\]#"
TERMINAL_PROMPT = '(?i)terminal type\?'
TERMINAL_TYPE = 'vt100'
# This is the prompt we get if SSH does not have the remote host's public key stored in the cache.
SSH_NEWKEY = '(?i)are you sure you want to continue connecting'

lock_file = "%s/sshscheduler.lock" % os.getenv("HOME")

settings = { "simulate": False, "default_user": None }
default_job_conf = { "color": None, "print_output": False, "command_timeout": None, "user": None, "return_values": {"pass": [0], "fail": [] } }
default_command_conf = { "command_timeout": None, "return_values": {"pass": [], "fail": [] } }
default_session_conf = { "name_id": None, }

session_jobs = None
threads = []
threads_to_kill = []
stopped = False
fatal_abort = False
gather_results = True
sigint_ctrl = False
print_t = None
print_commands = False
print_command_output = None
global_timeout_expired = 0



class StdoutSplit:
    """Write string to both stdout and terminal log file"""

    def __init__(self, output_file=None, print_to_stdout=False, line_prefix=None, color=None):
        self.content = []
        self.stdout = sys.stdout
        self.verbose = 0
        self.print_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.output_file = output_file
        self.line_prefix = line_prefix          # This is for the output from the commands
        self.color = color
        self.print_to_stdout = print_to_stdout  # If the write-function should print output to stdout
        self.terminal_print_cache = ""
        self.terminal_print_cache_lines = 0

    def write(self, string):
        self.write_lock.acquire() # will block if lock is already held
        if self.line_prefix:
            if (print_command_output is True or (self.print_to_stdout and print_command_output is None)):
                prefix = self.line_prefix
                prefixed_string = ""
                line_count = 0
                thread_prefix = self.get_thread_prefix()
                terminal_prefix = "%-25s | " % "COMMAND OUTPUT"
                prefix = terminal_prefix + prefix
                if self.color and termcolor:
                    prefix = colored(prefix, self.color)

                string = string.replace("\r", "")
                for line in string.splitlines():
                    prefixed_string += prefix + line + "\n"
                    line_count += 1
                self.terminal_print_cache += prefixed_string
                self.terminal_print_cache_lines += line_count
        else:
            print(string, file=self.stdout, end="")
        if self.output_file:
            try:
                print(string, file=self.output_file, end="")
            except ValueError, v:
                print("write(%s) ValueError when printing: %s\n" % (self.get_thread_prefix(), str(string)), file=self.stdout, end="")
        self.write_lock.release()

    def flush(self, now=False):
        if self.output_file:
            self.output_file.flush()

        if self.terminal_print_cache:
            # More than 4 lines before printing
            if self.terminal_print_cache_lines > 0 or now:
                print(self.terminal_print_cache, file=self.stdout, end="")
                self.terminal_print_cache = ""
                self.terminal_print_cache_lines = 0

    def close(self):
        self.flush(now=True)
        if self.output_file:
            self.output_file.close()

    def get_thread_prefix(self):
        import datetime
        t = datetime.datetime.now()
        t = "%s:%03d" % (t.strftime("%H:%M:%S"), t.microsecond/1000)
        t_out = "%s : %10s | " % (t, threading.current_thread().name)
        return t_out

    def print_t(self, *arg, **kwargs):
        """
        Thread safe function that prints the values prefixed with a timestamp and the
        ID of the calling thread. Output is written to stdout and terminal log file
        """
        print
        self.print_lock.acquire() # will block if lock is already held
        arg = list(arg)

        if "verbose" in kwargs:
            # Verbose level is too high, so do not print
            if kwargs["verbose"] and kwargs["verbose"] > self.verbose:
                self.print_lock.release()
                return

        # Handles newlines and beginning and end of format string so it looks better with the Thread name printed
        newline_count = 0
        if len(arg) > 0:
            # Removing leading newlines
            if len(arg[0]) > 0:
                while arg[0][0] == "\n":
                    # Print the thread prefix only
                    print(self.get_thread_prefix())
                    arg[0] = arg[0][1:]
                    if arg[0] is "":
                        break
                # Count newlines at the end, and remove them
                while not arg[0] is "" and arg[0][-1] == "\n":
                    newline_count += 1
                    arg[0] = arg[0][:-1]

        if not (len(arg) == 1 and len(arg[0]) == 0):
            # Print timestamp and thread name
            thread_prefix = self.get_thread_prefix()
            if "prefix_color" in kwargs and termcolor:
                thread_prefix = colored(thread_prefix, kwargs["prefix_color"])

            print(thread_prefix, end="")

            # Print the strings
            while True:
                if "color" in kwargs and termcolor:
                    if len(arg) > 1:
                        cprint("When using colors, print only accepts one string argument, %d was given!" % len(arg), color='red')
                        traceback.print_stack()
                    else:
                        try:
                            cprint(*arg, color=kwargs["color"])
                            if self.output_file:
                                self.output_file.write(thread_prefix)
                            break
                        except Exception, e:
                            print("cprint failed")
                            traceback.print_exc()
                            for a in arg:
                                print("Arg:", a)
                print(*arg)
                break

        if newline_count:
            print("\n" * newline_count)
        self.print_lock.release()

# Replace stdout with StdoutSplit
sys.stdout = StdoutSplit(print_to_stdout=True)
print_t = sys.stdout.print_t

class scpJob(pxssh):
    def __init__(self, logfile=None):
        pxssh.__init__(self, logfile=logfile)
        pxssh._spawn(self, "/bin/bash")
        self.set_unique_prompt()

class Job(Thread):

    def __init__(self, host_conf, session_job_conf, commands):
        Thread.__init__(self)
        self.conf = host_conf
        self.host = host_conf["host"]
        self.user = host_conf["user"]
        self.commands = commands
        #self.timeout = 2
        self.killed = False
        self.command_timed_out = False
        self.session_job_conf = session_job_conf
        self.logfile = None
        self.logfile_name = None
        self.fout = None
        self.last_command = None
        self.login_sucessfull = False
        if self.conf.has_key("logfile_name"):
            self.logfile_name = self.conf["logfile_name"]
            if self.session_job_conf and self.session_job_conf["name_id"]:
                self.logfile_name = "%s_%s" % (self.session_job_conf["name_id"], self.logfile_name)
            self.fout = file(os.path.join(self.conf["log_dir"], self.logfile_name), "w")

    def kill(self):
        if hasattr(self, 'child') and self.child is not None:
            self.killed = True
            # Necessary to shut down server process that's still running
            try:
                #self.child.close(force=True)
                #self.child.kill(15)
                self.child.terminate(force=True)
            except KeyboardInterrupt:
                print_t("kill(): Caught KeyboardInterrupt")
            except OSError, o:
                print_t("kill(): Caught OSError:", o)

    def run(self):
        self.name = threading.current_thread().name

        if self.logfile_name:
            line_prefix = self.conf["host"]
            if "id" in self.conf:
                line_prefix += " : %s" % self.conf["id"]
            self.logfile = StdoutSplit(self.fout, line_prefix="%s ::  " % line_prefix, color=self.conf["color"])

        if self.conf["type"] == "ssh":
            self.child = self.ssh_login(self.user, self.host)
            if not self.login_sucessfull:
                if not settings["simulate"]:
                    print_t("Failed to connect to host %s" % self.host, color='red')
                    print_t("child.timeout: %s" % self.child.timeout, color='red')
                    abort_job(results=False, fatal=True)
                    return
        elif self.conf["type"] == "scp":
            self.child = scpJob(logfile=self.logfile)

        self.execute_commands()
        if not settings["simulate"]:
            self.handle_commands_executed()
        if print_commands:
            print_t("Jobs on %-9s have finished." % self.host, verbose=2)

    def read_command_output(self, timeout=0):
        ret = ""
        if not self.killed:
            while True:
                try:
                    # Read the output to log. Necessary to get the output
                    ret += self.child.read_nonblocking(size=1000, timeout=timeout)
                    #print_t("read_command_output:", ret)
                except pexpect.TIMEOUT, e:
                    #print_t("read_command_output - TIMEOUT:", timeout)
                    if timeout != 0:
                        timeout = 0
                        continue
                    break
                except pexpect.EOF, e:
                    # No more data
                    #print_t("read_command_output - No more data:", e)
                    break
                except select.error:
                    # (9, 'Bad file descriptor')
                    pass
                except OSError as o:
                    print_t("OSError:", e, verbose=1)
                    if sys.stdout.verbose:
                        traceback.print_exc()
                    break
        return ret

    def execute_commands(self):
        print_output = self.logfile.print_to_stdout

        for c in self.commands:
            self.command_timed_out = False
            self.logfile.print_to_stdout = print_output
            command = c["command"]
            if self.session_job_conf and c.has_key("substitute_id"):
                #print_t("Substituting into '%s' : '%s'" % (command, self.session_job_conf["substitutions"][c["substitute_id"]]))
                try:
                    command = command % self.session_job_conf["substitutions"][c["substitute_id"]]
                except KeyError, k:
                    print_t("Encountered KeyError when inserting subsitution settings: %s" % k, color="red")
                    abort_job(results=False, fatal=True)
                    sys.exit(1)
            # Execute commands in separate bash? Need if using pipes..
            command = "/bin/bash -c '%s'" % command

            if print_commands:
                print_t("Command on %-9s: \"%s\"%s" % (self.host, command, " with timeout: %s sec" % c["command_timeout"] if c["command_timeout"] else "" ),
                        color='yellow' if settings["simulate"] else None, prefix_color=self.conf["color"])
            if stopped:
                print_t("Session job has been stopped before all commands were executed!", color='red', prefix_color=self.conf["color"])
                return
            if settings["simulate"]:
                continue

            if "print_output" in c:
                self.logfile.print_to_stdout = c["print_output"]

            self.last_command = command
            try:
                # Clear out the output
                #self.read_command_output()
                self.child.sendline(command)
            except OSError as o:
                print_t("OSError: %s" % o, color="red")
                if sys.stdout.verbose:
                    traceback.print_exc()
            except Exception, e:
                print_t("Exception: %s" % str(e), color="red")
                if sys.stdout.verbose:
                    traceback.print_exc()
                pass

            timeout = c["command_timeout"]
            if timeout is None:
                timeout = self.child.timeout

            return_value = self.wait_for_command_exit(c, timeout)

            if not self.killed and not self.command_timed_out:
                if (c["return_values"]["pass"] and not return_value in c["return_values"]["pass"]) or (c["return_values"]["fail"] and return_value in c["return_values"]["fail"]):
                    print_t("Command on '%-9s' returned with status: %s: '%s', passing return values: %s, failing return values: %s" % \
                                (self.host, str(return_value), self.last_command, str(c["return_values"]["pass"]), str(c["return_values"]["fail"])), color='red')
                    print_t("Aborting session!", color="red")
                    abort_job(results=False, fatal=True)

    def wait_for_command_exit(self, command, timeout):
        def get_last_return_value():
            try:
                # Clear out the output
                self.child.sendline("ret=$? && echo $ret && (exit $ret)")
                self.child.prompt()
                import os, re
                m = re.match("ret=\$\? && echo \$ret && \(exit \$ret\).*(\d)", self.child.before, flags=re.DOTALL)
                if m:
                    return int(m.group(1))
                else:
                    print_t("Did not match return value regex: '%s', bug?!" % self.child.before, color="red")
                    return None
            except OSError as o:
                print_t("OSError: %s" % o, color="red")
                if sys.stdout.verbose:
                    traceback.print_exc()
        while True:
            index = 0
            try:
                ret = self.child.prompt(timeout=timeout)
                if ret is False:
                    index = 2
            except pexpect.ExceptionPexpect, e:
                # Reached an unexpected state in read_nonblocking()
                # End of File (EOF) in read_nonblocking(). Very pokey platform
                #print_t("ExceptionPexpect:", e)
                #print_t("ExceptionPexpect:")
                break
            except Exception, e:
                index = None
                print_t("Exception:: %s" % str(e), color="red")
                traceback.print_exc()
            # Timeout
            if index == 2:
                # This means the default timeout has expanded. Since no timeout is specified in config, continue
                if command["command_timeout"] is None:
                    continue
                else:
                    # Send SIGINT to stop command
                    self.child.sendintr()
                    self.command_timed_out = True
                    print_t("Command stopped by timeout '%d', '%s'" % (timeout, self.last_command), color="yellow", verbose=1)
                    # Continue to expect next prompt
            else:
                # Command finished and prompt was read
                break
        if not self.killed and not self.command_timed_out:
            return get_last_return_value()
        return None

    def handle_commands_executed(self):
        try:
            #print_t("handle_commands_executed killed:", self.killed)
            if not self.killed:
                if self.conf["type"] == "ssh":
                    self.child.logout()
                else:
                    self.child.sendline("exit")
        except OSError as o:
            print_t("handle_commands_executed() Caught OSError: %s" % o, color="red")
            if sys.stdout.verbose:
                traceback.print_exc()

        # Wait for process to exit
        try:
            self.child.wait()
        except pexpect.ExceptionPexpect:
            pass

        # The job was killed by the script
        if self.killed:
            if self.child.exitstatus != 130:
                print_t("Command aborted but exitstatus is not 130: '%s' !?" % (str(self.child.exitstatus)), color="red")

            should_be_killed = self.conf.has_key("kill") and self.conf["kill"]
            if not should_be_killed:
                if sigint_ctrl:
                    print_t("Command on '%-9s' was killed by the script. (Session aborted with CTRL-c by user) (Status: %s) : '%s'" % \
                                (self.host, str(self.child.exitstatus), self.last_command), color='yellow')
                elif global_timeout_expired:
                    print_t("Command on '%-9s' was killed by the script because the global timeout expired (%d). (Status: %s) : '%s'" % \
                                (self.host, global_timeout_expired, str(self.child.exitstatus), self.last_command), color='yellow')
                else:
                    print_t("Command on '%-9s' was killed by the script, but that is not as expected. (Status: %s) : '%s' " % \
                                (self.host, str(self.child.exitstatus), self.last_command), color='red')
            else:
                print_t("Command on '%-9s' was killed by the script. (Status: %s) : '%s'" % \
                            (self.host, str(self.child.exitstatus), self.last_command), color='yellow', verbose=1)

    def ssh_login(self, user, host):
        if settings["simulate"]:
            return None

        child = pxssh(timeout=30, logfile=self.logfile)
        count = 0
        while True:
            try:
                host, user = get_host_and_user(self.host, self.user)
                print_t("Connecting to '%s@%s'" % (user, host), verbose=2)
                count += 1
                child.login(host, user, None)
                self.login_sucessfull = True
                break
            except pexpect.TIMEOUT, e:
                if count >= 3:
                    print_t("Failed to connect after %d attempts: %s" % (count, str(e)), color="red")
                    return child
                print_t("Failed to connect to '%s'. Tries left: %d" % (self.host, 3 - count), color="yellow")
                child.pid = None
            except Exception, e:
                print_t("Failed to connect:", e)
                return child
        # Success
        return child

def abort_job(results=True, fatal=False):
    global stopped, fatal_abort, gather_results
    stopped = True
    fatal_abort = True if fatal else fatal_abort
    gather_results = results
    print_t("Jobs to kill: %s" % (len(threads) + len(threads_to_kill)), color='red' if not results else None)
    kill_threads(threads)
    kill_threads(threads_to_kill)

def kill_threads(threads_list):
    for t in list(threads_list):
        try:
            if hasattr(t, 'child') and t.child is not None and t.child.isalive():
                t.child.read_nonblocking(size=1000, timeout=0)
        except (pexpect.TIMEOUT, pexpect.EOF) as e:
            #print_t("Exception: %s : %s" % (type(e), e))
            # pexpect.TIMEOUT raised if no new data in buffer
            # pexpect.EOF raised when it reads EOF
            pass
        except select.error:
            # (9, 'Bad file descriptor')
            pass
        except OSError as o:
            print_t("kill_threads() Caught OSError:", e, verbose=1)
            if sys.stdout.verbose:
                traceback.print_exc()
        except IOError as o:
            print_t("kill_threads() Caught IOError:", e, verbose=1)
        print_t("Killing thread '%s' running on '%s' command: %s" % (t.name, t.host, str(t.last_command)), verbose=2)
        # Kills the pexpect child
        t.kill()
        #threads_list.remove(t)

def join_current_threads(timeout=None):
    global threads
    ret = join_threads(threads, timeout=timeout)
    threads = []
    return ret

def join_threads(threads, timeout=None):
    print_t("Joining threads (%d): with timeout: %s %s" % (len(threads), str(timeout), str([t.name for t in threads])), verbose=1)
    start_time = time.time()

    for t in threads:
        print_t("Join thread:", t.name, verbose=2)
        while True:
            try:
                # Thread hasn't beens started yet
                if t.ident is None:
                    time.sleep(1)
                else:
                    t.join(1)
                    if not t.isAlive():
                        break
            except KeyboardInterrupt, e:
                print_t("SIGTERM Received", color='red', verbose=1)
                return False

            if timeout:
                if start_time + timeout < time.time():
                    print_t("Timeout (%s) exceeded, stopping jobs" % str(timeout), color="green")
                    global global_timeout_expired
                    global_timeout_expired = timeout
                    if not (fatal_abort or sigint_ctrl):
                        abort_job(results=True)
                    return True
    for t in threads:
        if t.isAlive():
            print_t("THREAD IS STILL ALIVE:", t.name)
    return True


def handle_only_one_job_in_execution():
    if os.path.isfile(lock_file):
        f = open(lock_file, 'r')
        content = f.read()
        f.close()
        return content
    f = open(lock_file, 'w+')
    date = datetime.now().strftime("%Y-%m-%d-%H%M-%S")
    f.write("Test name: %s\n" % settings["session_name"])
    f.write("Started at: %s\n" % date)
    f.close()
    return None

def setup_log_directories():
    # Setup directories for storing results and log files
    job_date = datetime.now().strftime("%Y-%m-%d-%H%M-%S")
    jobname_dir = "%s/%s" % (settings["results_dir"], settings["session_name"])
    results_dir = "%s/%s" % (jobname_dir, job_date)
    log_dir = "%s/logs" % results_dir
    last_dir = "%s/last" % jobname_dir
    last_log_dir = "%s/log" % last_dir
    os.makedirs(log_dir)
    try:
        os.makedirs(last_log_dir)
    except:
        pass
    return results_dir, log_dir, last_dir, last_log_dir


def run_session_job(session_job_conf, jobs):
    global stopped, threads, threads_to_kill, sigint_ctrl
    session_job_start_time = datetime.now()

    if session_job_conf:
        print_t("Running session job '%s' (%s) (Timeout: %s) at %s %s" % (session_job_conf["name_id"],
                                                                          session_job_conf["description"],
                                                                          session_job_conf["timeout_secs"],
                                                                          str(session_job_start_time),
                                                                          "in test mode" if settings["simulate"] else ""),
                color='yellow' if settings["simulate"] else 'green')
    current_index = 0
    for i in range(len(jobs)):
        if stopped:
            break
        current_index = i
        job = jobs[i]

        if job[0].has_key("host"):
            job[0]["log_dir"] = last_log_dir
            job[0]["last_dir"] = last_dir

            # Prefix logfile name with session job name_id
            if "logfile" in job[0]:
                job[0]["logfile_name"] = job[0]["logfile"]

            t = Job(job[0], session_job_conf, job[1])
            if job[0].has_key("kill") and job[0]["kill"] is True:
                threads_to_kill.append(t)
            else:
                threads.append(t)
            t.start()
            # We must wait on this job immediately before continuing
            if job[0].has_key("wait") and job[0]["wait"]:
                join_threads([t])

        elif job[0].has_key("sleep"):
            try:
                time.sleep(float(job[0]["sleep"]))
            except KeyboardInterrupt, i:
                abort_job(results=False)
        elif job[0].has_key("wait"):
            timeout = None
            if session_job_conf:
                timeout = session_job_conf["timeout_secs"]
                print_t("Waiting for jobs with timeout: %s" % str(session_job_conf["timeout_secs"]), color='green', verbose=1)
            else:
                print_t("Waiting for jobs", color='green', verbose=1)

            # Wait for all previous jobs before continuing
            if join_current_threads(timeout=timeout):
                # Job was not aborted by SIGTERM. Kill the jobs denoted with kill
                print_t("Jobs completed uninterupted. Killing threads: %d" % len(threads_to_kill), color='green')
                # Sleep to let remaining packets arrive before killing tcpdump
                time.sleep(1)
                stopped = True
                if not (global_timeout_expired or sigint_ctrl):
                    kill_threads(threads_to_kill)
                break
            else:
                # Shouldn't reach this code any longer
                print_t("Test interrupted by CTRL-c!", color='red')
                sigint_ctrl = True
                abort_job()
                break

    end_time = datetime.now()

    if gather_results:
        # Gather results
        if session_job_conf:
            print_t("Session job '%s' has finished." % session_job_conf["name_id"], color='green')

        if current_index + 1 != len(jobs):
            print_t("Saving files to: %s" % results_dir, color="green")
            threads = []
            stopped = False
            for i in range(current_index + 1, len(jobs)):
                job = jobs[i]
                # We only want the scp jobs here
                if not job[0]["type"] == "scp":
                    continue

                # Prefix logfile name with session job name_id
                if "logfile" in job[0]:
                    job[0]["logfile_name"] = job[0]["logfile"]

                conf = job[0]
                conf["log_dir"] = last_log_dir

                target_filename = conf["target_filename"]
                # Prefix name with session job name_id
                if session_job_conf and session_job_conf["name_id"]:
                    target_filename = "%s_%s" % (session_job_conf["name_id"], target_filename)

                target_file = "%s/%s" % (results_dir, target_filename)
                link_file = "%s/%s" % (last_dir, target_filename)
                host, user = get_host_and_user(conf["remote_host"], conf["user"])
                scp_cmd = "scp %s@%s:%s %s" % (user, host, conf["filename"], target_file)

                ln_cmd = "ln %s %s" % (target_file, link_file)

                cmd_scp_dict = copy.deepcopy(default_command_conf)
                cmd_ln_dict = copy.deepcopy(default_command_conf)
                cmd_scp_dict["command"] = scp_cmd
                cmd_ln_dict["command"] = ln_cmd
                cmd_scp_dict["return_values"].update(conf["return_values"])
                cmd_ln_dict["return_values"].update(conf["return_values"])
                commands = [cmd_scp_dict, cmd_ln_dict]
                t = Job(job[0], session_job_conf, commands)
                threads.append(t)
                t.start()

            if not join_current_threads():
                print_t("Last join interrupted by CTRL-c")

            # Copy logs to proper directory
            cmd = "cp %s/*.log %s/" % (last_log_dir, log_dir)
            out = os.popen(cmd).read()

        if session_job_conf:
            line = "Execution of session job '%s' finished in %s seconds at %s" % (session_job_conf["name_id"], str((end_time - session_job_start_time)), str(end_time))
            print_t("=" * len(line), color='blue')
            print_t(line, color='blue')
            print_t("=" * len(line), color='blue')
    else:
        print_t("Session job was aborted before being started. No results gathered")

    print_t("Waiting for jobs to kill", verbose=1)
    join_threads(threads_to_kill)
    threads_to_kill = []

def get_host_and_user(host, user):
    import os, re
    m = re.match("(.+)@(.+)", host)
    if m:
        user = m.group(1)
        host = m.group(2)
    return host, user

def parse_job_conf(filename):
    global settings
    global session_jobs
    jobs = []
    job = None
    f = open(filename, 'r')
    lines = f.readlines()
    eval_lines = ""
    for i in range(len(lines)):
        again = True
        # Remove content after #
        line = lines[i].split("#")[0].strip()
        if not line:
            continue
        try:
            eval_lines += line
            d = eval(eval_lines)
        except Exception, e:
            # Failed ot parse, append next line and try again
            #print_t("Failed to parse:", eval_lines)
            continue
        else:
            eval_lines = ""

        # The settings dict
        if d.has_key("settings"):
            settings.update(d)
            if not "session_name" in settings:
                settings["session_name"] = os.path.splitext(filename)[0]
            if settings["default_user"] is None:
                settings["default_user"] = os.getenv('USER')
        # New host
        elif d.has_key("host"):
            job_conf = copy.deepcopy(default_job_conf)
            job_conf.update(d)
            if job_conf["user"] is None:
                job_conf["user"] = settings["default_user"]
            if job is not None:
                jobs.append(job)
            job = [job_conf, []]
        # Command for host
        elif d.has_key("command"):
            cmd_conf = copy.deepcopy(default_command_conf)
            cmd_conf.update(d)
            if not "print_output" in d:
                cmd_conf["print_output"] = job[0]["print_output"]
            if "return_values" in d:
                cmd_conf["return_values"] = default_command_conf["return_values"].copy()
                cmd_conf["return_values"].update(d["return_values"])
            else:
                cmd_conf["return_values"] = job[0]["return_values"].copy()

            if not "command_timeout" in d:
                cmd_conf["command_timeout"] = job[0]["command_timeout"]

            job[1].append(cmd_conf)
        # Do a sleep or wait for all previous jobs
        elif d.has_key("sleep") or d.has_key("wait") or d.has_key("cleanup"):
            if job is not None:
                jobs.append(job)
            d["type"] = None
            jobs.append([d])
            job = None

        elif d.has_key("session_jobs"):
            session_jobs = d
            for sj in d["session_jobs"]:
                if not "timeout_secs" in sj:
                    sj["timeout_secs"] = d["default_session_job_timeout_secs"]
                if not "substitutions" in sj:
                    continue
                for sub in sj["substitutions"].keys():
                    # If it refers to default settings, add these to the settings dict
                    if "default_settings" in d:
                        # Exists on both default settings and sub
                        if sub in d["default_settings"]:
                            sub_settings = copy.deepcopy(d["default_settings"][sub])
                            sub_settings.update(sj["substitutions"][sub])
                            sj["substitutions"][sub] = sub_settings

                        diff = set(d["default_settings"].keys()) - set(sj["substitutions"].keys())
                        for key in diff:
                            # Only in default settings, so add to sub
                            sj["substitutions"][key] = d["default_settings"][key]
    if eval_lines:
        print_t("You have a syntax error in the job config!", color="red")
        print_t("Failed to parse config lines: %s" % eval_lines, color="red")
        sys.exit(0)

    # Add last job
    if job is not None:
        jobs.append(job)
    return jobs

def to_bool(value):
    """
       Converts 'something' to boolean. Raises exception for invalid formats
           Possible True  values: 1, True, "1", "TRue", "yes", "y", "t"
           Possible False values: 0, False, None, [], {}, "", "0", "faLse", "no", "n", "f", 0.0, ...
    """
    if str(value).lower() in ("yes", "y", "true",  "t", "1"): return True
    if str(value).lower() in ("no",  "n", "false", "f", "0"): return False
    print('Invalid value for boolean conversion: ' + str(value))
    sys.exit(0)

class SignalHandler(Thread):

    active_handlers = []

    def __init__(self, call_count=0):
        self.call_count = call_count

    def handle_signal(self, signal, frame):
        self.call_count += 1
        handler = SignalHandler(self.call_count)
        Thread.__init__(handler)
        SignalHandler.active_handlers.append(handler)
        handler.start()

    def run(self):
        global sigint_ctrl
        print_t("Session interrupted by SIGINT signal. Killing threads...", color="red")
        sigint_ctrl = True
        try:
            abort_job()
        except Exception, e:
            print_t("signal_handler - Caught Excepytion: %s!" % str(e), color="red")
        except:
            print_t("signal_handler - Caught unspecified error!", color="red")
            pass
        for i, h in enumerate(SignalHandler.active_handlers):
            if self is h:
                del SignalHandler.active_handlers[i]

if __name__ == "__main__":
    signal_handler = SignalHandler()
    signal.signal(signal.SIGINT, signal_handler.handle_signal)

    argparser = argparse.ArgumentParser(description="Run test sessions")
    argparser.add_argument("-v", "--verbose",  help="Enable verbose output.", action='count', default=0, required=False)
    argparser.add_argument("-s", "--simulate",  help="Simulate only, do not execute commands.", action='store_true', required=False)
    argparser.add_argument("-c", "--print-commands",  help="Print the commands being executed.", action='store_true', required=False)
    argparser.add_argument("-p", "--print-output", metavar='boolean string', help="Print the terminal output from all the commands to stdout. This overrides any settings in the config file.", required=False)
    argparser.add_argument("file", help="The file containing the the commands to run")
    args = argparser.parse_args()

    sys.stdout.verbose = args.verbose

    if args.print_output:
        print_command_output = to_bool(args.print_output)

    jobs = parse_job_conf(args.file)

    if args.simulate:
        settings["simulate"] = True

    if args.print_commands:
        print_commands = True

    if handle_only_one_job_in_execution() is not None:
        print("Lock file is present (%s). Either a job is currently running, "
              "or a lock file from a previous job was not correctly removed." % lock_file)
        f = open(lock_file, "r")
        print("Lock file content:", f.read())
        f.close()
        sys.exit()

    results_dir, log_dir, last_dir, last_log_dir = setup_log_directories()
    sys.stdout.output_file = open(os.path.join(last_log_dir, "terminal.log"), 'w+')

    cmd = "rm -f %s/*.* %s/*.*" % (last_dir, last_log_dir)
    out = os.popen(cmd).read()

    session_start_time = datetime.now()
    print_t("Starting session '%s' at %s %s" % (settings["session_name"], str(session_start_time),
                                                "in test mode" if settings["simulate"] else ""),
            color='yellow' if settings["simulate"] else 'green')

    # session_jobs defined in config
    if session_jobs:
        for i, session_job in enumerate(session_jobs["session_jobs"]):
            if fatal_abort or sigint_ctrl:
                break
            stopped = False
            global_timeout_expired = 0
            if i != 0 and session_jobs["delay_between_session_jobs_secs"]:
                print_t("Sleeping %d seconds before next session job." % session_jobs["delay_between_session_jobs_secs"])
                if not settings["simulate"]:
                    time.sleep(session_jobs["delay_between_session_jobs_secs"])
            run_session_job(session_job, jobs)
    else:
        run_session_job(None, jobs)

    if sigint_ctrl:
        print_t("Session stopped by SIGINT signal")

    if fatal_abort:
        print_t("\nSession was aborted!", color="red")

    end_time = datetime.now()
    print_t("\n")
    color = "blue"
    if fatal_abort:
        color = "red"
    line = "Execution of session '%s' finished in %s seconds at %s" % (settings["session_name"], str((end_time - session_start_time)), str(end_time))
    print_t("*" * len(line), color=color)
    print_t("*" * len(line), color=color)
    print_t(line, color=color)
    print_t("*" * 110, color=color)
    print_t("*" * 110, color=color)

    sys.stdout.close()
    os.remove(lock_file)

