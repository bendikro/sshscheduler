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

import os, sys, time, re, argparse, threading, traceback, select
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

    def cprint(*arg, **kwargs):
        print(*arg)

    def colored(text, color):
        return text


def check_pexpect_version():
    try:
        version = float(pexpect.__version__)
        if version < 2.4:
            print_t("Minimum required pexpect version is 2.4. Current installed version is %.1f" % version, color="red")
            sys.exit(0)
    except:
        print_t("Error occured when checking pexpect version!")

settings = {"session_name": "sshscheduler_example_session", "default_user": None, "results_dir": "results",
            "simulate": False, "resume": False, "gather_results_on_cancel": True}
default_session_jobs_conf = {"session_jobs": None, "default_session_job_timeout_secs": None,
                             "delay_between_session_jobs_secs": 0, "default_settings": None}
default_job_conf = {"type": None, "color": None, "print_output": False, "command_timeout": None, "user": None,
                    "cleanup": False, "wait": False, "id": "", "return_values": {"pass": [0], "fail": [], "retry": []}}
default_command_conf = {"command_timeout": None, "return_values": {"pass": [], "fail": [], "retry": []},
                        "commands_while_running": None}
default_wait_sleep_conf = {"sleep": 0, "type": None}

threads = []
threads_to_kill = []

stopped = False
fatal_abort = False
gather_results = True
sigint_ctrl = False
retry_session_job = False

print_t = None
print_commands = False
print_command_output = None
no_terminal_output = False

global_timeout_expired = 0
session_start_time = None
session_end_time = None

lockFileHandler = None
lock_file = "%s/sshscheduler.lock" % os.getenv("HOME")
signal_handler_running = False


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
        self.write_lock.acquire()  # will block if lock is already held
        try:
            # In case of any errors in do_write function
            self.do_write(string)
        except TypeError, e:
            print("TypeError: %s" % str(e), file=self.stdout)
            traceback.print_exc()
        except:
            print("Unspecified Exception!", file=self.stdout)
            traceback.print_exc()
        self.write_lock.release()

    def do_write(self, string):
        if self.line_prefix:
            # This is output from a command
            string = string.replace("\r", "")

            if not no_terminal_output and \
                    (print_command_output is True or (self.print_to_stdout and print_command_output is None)):
                prefixed_string = ""
                line_count = 0
                prefix = "%s : %12s | " % (self._get_time_now(), self.line_prefix)
                if self.color:
                    prefix = colored(prefix, self.color)
                for line in string.splitlines():
                    prefixed_string += prefix + line + "\n"
                    line_count += 1
                self.terminal_print_cache += prefixed_string
                self.terminal_print_cache_lines += line_count

        elif not no_terminal_output:
            print(string, file=self.stdout, end="")

        if self.output_file and not self.output_file.closed:
            try:
                print(string, file=self.output_file, end="")
                self.output_file.flush()
            except ValueError, v:
                print("write(%s) ValueError (%s) when printing: '%s'" % (self._get_thread_prefix(), str(v),
                                                                         str(string)), file=self.stdout)
                print("STACK:", file=self.stdout)
                traceback.print_exc()

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

    def _get_time_now(self):
        t = datetime.now()
        t = "%s:%03d" % (t.strftime("%H:%M:%S"), t.microsecond / 1000)
        return t

    def _get_thread_prefix(self, verbose=None, color=None):
        t = self._get_time_now()
        name = threading.current_thread().name
        if verbose:
            name = "V=%d %10s" % (verbose, name)
        t_out = "%s : %14s | " % (t, name)
        if color:
            t_out = colored(t_out, color=color)
        return t_out

    def print_t(self, *arg, **kwargs):
        self.print_lock.acquire()  # will block if lock is already held
        try:
            self._print_t(*arg, **kwargs)
        except TypeError, e:
            print("TypeError in print_t: %s" % (str(e)), file=self.stdout)
            traceback.print_exc()
        except:
            print("Exception in print_t:", file=self.stdout)
            traceback.print_exc()
        finally:
            self.print_lock.release()

    def _print_t(self, *arg, **kwargs):
        """
        Thread safe function that prints the values prefixed with a timestamp and the
        ID of the calling thread. Output is written to stdout and terminal log file
        """
        # Convert from tuple to list
        arg = list(arg)
        print_str = ""
        verbose = None

        if "verbose" in kwargs:
            # Verbose level is too high, so do not print
            if kwargs["verbose"] and kwargs["verbose"] > self.verbose:
                return
            else:
                verbose = kwargs["verbose"]

        prefix_color = None
        if "prefix_color" in kwargs:
            prefix_color = kwargs["prefix_color"]
        prefix_str = self._get_thread_prefix(verbose=verbose, color=prefix_color)

        # Handles newlines and beginning and end of format string so it looks better with the Thread name printed
        newline_count = 0
        if len(arg) > 0:
            # Removing leading newlines
            if len(arg[0]) > 0:
                while arg[0][0] == "\n":
                    # Print the thread prefix only
                    print_str += prefix_str + "\n"
                    arg[0] = arg[0][1:]
                    if arg[0] is "":
                        break
                # Count newlines at the end, and remove them
                while not arg[0] is "" and arg[0][-1] == "\n":
                    newline_count += 1
                    arg[0] = arg[0][:-1]

        def add_line(l):
            text = prefix_str
            if "color" in kwargs:
                try:
                    text += colored(l, color=kwargs["color"])
                except Exception:
                    text += l
            else:
                text += l
            return text

        # Try to format string
        if len(arg) > 1:
            fmt = arg.pop(0)
            try:
                text = fmt % tuple(arg)
            except TypeError:
                # import inspect
                # frame, filename, line_number, function_name, lines, index = inspect.getouterframes(inspect.currentframe())[2]
                # cprint("Invalid input to print_t function!\nFile: '%s'\nFunction: '%s' on line: %d" % (filename, function_name, line_number), color='red')
                # traceback.print_stack()
                text = fmt
                for a in arg:
                    text += " " + str(a)
        else:
            text = arg[0]

        if "split_newlines" in kwargs and kwargs["split_newlines"] is True:
            lines = text.splitlines()
            for u in range(0, len(lines)):
                if u != 0:
                    print_str += "\n"
                print_str += add_line(lines[u])
        else:
            print_str += add_line(text)

        if newline_count:
            print_str += ("\n" + prefix_str) * newline_count

        print(print_str)

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
        self.host_and_id = "%s%s" % (host_conf["host"], ":" + host_conf["id"] if host_conf["id"] else "")
        self.name_and_host = None
        self.user = host_conf["user"]
        self.commands = commands
        self.killed = False
        self.command_timed_out = False
        self.session_job_conf = session_job_conf
        self.logfile = None
        self.logfile_name = None
        self.fout = None
        self.last_command = None
        self.login_sucessfull = False
        if "logfile_name" in self.conf:
            self.logfile_name = self.conf["logfile_name"]
            if self.session_job_conf and self.session_job_conf["name_id"]:
                self.logfile_name = "%s_%s" % (self.session_job_conf["name_id"], self.logfile_name)
            self.fout = file(os.path.join(self.conf["log_dir"], self.logfile_name), "w")

    def kill(self):
        print_t("kill() on %s" % self.name, verbose=3)
        self.killed = True
        if hasattr(self, 'child') and self.child is not None:
            # Necessary to shut down server process that's still running
            try:
                if "sigint_before_exit" in self.conf:
                    print_t("Sending SIGINT %d times and sleeping %d seconds before closing connection." %
                            (self.conf["sigint_before_exit"]["count"], self.conf["sigint_before_exit"]["sleep"]),
                            verbose=2)
                    if self.child.isalive():
                        for i in range(self.conf["sigint_before_exit"]["count"]):
                            self.child.sendintr()
                        time.sleep(self.conf["sigint_before_exit"]["sleep"])
                self.child.close(force=True)
            except KeyboardInterrupt:
                print_t("kill(): Caught KeyboardInterrupt")
            except OSError, o:
                print_t("kill(): Caught OSError:", o)
            except ValueError as e:
                print_t("kill(): Caught ValueError:", e)
                import traceback
                traceback.print_exc()
            except Exception as e:
                print_t("kill(): Caught Exception (%s): %s" % (type(e), str(e)))
                import traceback
                traceback.print_exc()

    def run(self):
        try:
            self.do_run()
        except SystemExit:
            print_t("%s - Caught SystemExit" % self.name)
            pass
        except:
            print_t("Exception in thread: %s" % self.name)
            traceback.print_exc()
        finally:
            pass

    def do_run(self):
        # self.name = "%s:%s:%s" % (threading.current_thread().name, self.host, self.conf["id"])
        self.name = threading.current_thread().name
        self.name_and_host = self.name + ":" + self.host_and_id

        print_t("Thread '%s' has started." % self.name, verbose=3)

        if self.logfile_name:
            line_prefix = "%-15s" % self.host_and_id
            self.logfile = StdoutSplit(self.fout, line_prefix="%s ::" % line_prefix, color=self.conf["color"])

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
            print_t("Jobs on '%-9s' have finished." % self.host_and_id, verbose=2)
        print_t("Thread '%s' has finished." % self.name, verbose=3)

    def read_command_output(self, timeout=0):
        ret = ""
        if not self.killed:
            while True:
                try:
                    # Read the output to log. Necessary to get the output
                    ret += self.child.read_nonblocking(size=1000, timeout=timeout)
                    # print_t("read_command_output:", ret)
                except pexpect.TIMEOUT:
                    # print_t("read_command_output - TIMEOUT:", timeout)
                    if timeout != 0:
                        timeout = 0
                        continue
                    break
                except pexpect.EOF:
                    # No more data
                    # print_t("read_command_output - No more data:", e)
                    break
                except select.error:
                    # (9, 'Bad file descriptor')
                    pass
                except OSError as o:
                    print_t("OSError:", o, verbose=1)
                    if sys.stdout.print_exceptions:
                        traceback.print_exc()
                    break
        return ret

    def execute_commands(self):
        global retry_session_job
        print_output = self.logfile.print_to_stdout

        for cmd in self.commands:
            self.command_timed_out = False
            self.logfile.print_to_stdout = print_output

            def execute_command(cmd_dict):
                command = cmd_dict["command"]
                if self.session_job_conf and "substitute_id" in cmd_dict:
                    try:
                        print_t("Substituting into '%s' : '%s' (%s)" %
                                (command, self.session_job_conf["substitutions"][cmd_dict["substitute_id"]], cmd_dict), verbose=3)
                        command = command % self.session_job_conf["substitutions"][cmd_dict["substitute_id"]]
                    except KeyError, k:
                        print_t("Encountered KeyError when inserting substitution settings: %s" % k, color="red")
                        print_t("command: '%s', substitute_id: '%s', substitution dict: '%s'" %
                                (command, cmd_dict["substitute_id"],
                                 self.session_job_conf["substitutions"][cmd_dict["substitute_id"]]))
                        abort_job(results=False, fatal=True)
                        sys.exit(1)
                    except ValueError, err:
                        print_t("Encountered ValueError when inserting substitution settings: %s" % err, color="red")
                        print_t("command: '%s', substitute_id: '%s', substitution dict: '%s'" %
                                (command, cmd_dict["substitute_id"],
                                 self.session_job_conf["substitutions"][cmd_dict["substitute_id"]]))
                        abort_job(results=False, fatal=True)
                        sys.exit(1)
                    except TypeError, err:
                        print_t("Encountered TypeError when inserting substitution settings: %s" % err, color="red")
                        print_t("command: '%s', substitute_id: '%s', substitution dict: '%s'" %
                                (command, cmd_dict["substitute_id"],
                                 self.session_job_conf["substitutions"][cmd_dict["substitute_id"]]))
                        abort_job(results=False, fatal=True)
                        sys.exit(1)

                # Execute commands in separate bash? Needed if using pipes..
                command = "/bin/bash -c '%s'" % command

                if stopped:
                    print_t("Session job has been stopped before all commands were executed!",
                            color='red', prefix_color=self.conf["color"])
                    return False

                if self.killed:
                    return False

                if print_commands:
                    print_t("Command on '%-15s': \"%s\"%s" %
                            (self.host_and_id, command, " with timeout: %s sec" %
                             cmd_dict["command_timeout"] if cmd_dict["command_timeout"] else ""),
                            color='yellow' if settings["simulate"] else None, prefix_color=self.conf["color"])
                if settings["simulate"]:
                    return True

                if "print_output" in cmd_dict:
                    self.logfile.print_to_stdout = cmd_dict["print_output"]

                self.last_command = command
                try:
                    # Clear out the output
                    # self.read_command_output()
                    self.child.sendline(command)
                except OSError as o:
                    print_t("OSError: %s" % o, color="red")
                    if sys.stdout.print_exceptions:
                        traceback.print_exc()
                except Exception, e:
                    print_t("Exception(%s): %s" % (type(e), str(e)), color="red")
                    if sys.stdout.print_exceptions:
                        traceback.print_exc()

                timeout = cmd_dict["command_timeout"]
                if timeout is None:
                    timeout = self.child.timeout

                return self.wait_for_command_exit(cmd_dict, timeout)

            def handle_command_return(ret_val, cmd_conf):
                if not self.killed and not self.command_timed_out:
                    # If == 0 -> We used all the attempts
                    if ret_val and cmd_conf["return_values"]["retry"] and cmd_conf["return_values"]["retry"][0] > 0:
                        cmd_conf["return_values"]["retry"][0] = cmd_conf["return_values"]["retry"][0] - 1
                        print_t("Job failed, but set to retry! New retry value: %d" %
                                cmd_conf["return_values"]["retry"][0], color="yellow")
                        global retry_session_job
                        retry_session_job = True
                        abort_job(results=False, fatal=False)
                    else:
                        if ((cmd_conf["return_values"]["pass"] and ret_val not in cmd_conf["return_values"]["pass"]) or
                                (cmd_conf["return_values"]["fail"] and ret_val in cmd_conf["return_values"]["fail"])):
                            print_t("Command on '%-9s' returned with status: %s: '%s', passing return values: %s, "
                                    "failing return values: %s" %
                                    (self.host_and_id, str(ret_val), self.last_command,
                                     str(cmd_conf["return_values"]["pass"]),
                                     str(cmd_conf["return_values"]["fail"])), color='red')
                            print_t("Logfile for failed host: %s" % self.logfile_name, color="yellow")
                            print_t("Aborting session!", color="red")
                            abort_job(results=False, fatal=True)

            if "foreach" in cmd:
                foreach_subs_id = cmd["substitute_id"]
                for each_sub_id in self.session_job_conf["substitutions"][foreach_subs_id]["foreach"]:
                    cmd_conf = copy.deepcopy(cmd)
                    cmd_conf["substitute_id"] = each_sub_id
                    return_value = execute_command(cmd_conf)
                    if return_value is False:
                        return
                    elif return_value is True:
                        continue
                    handle_command_return(return_value, cmd_conf)
            else:
                return_value = execute_command(cmd)
                if return_value is False:
                    return
                elif return_value is True:
                    continue
                handle_command_return(return_value, cmd)

    def wait_for_command_exit(self, command, timeout):
        def get_last_return_value():
            try:
                # Clear out the output
                self.child.sendline("ret=$? && echo $ret && (exit $ret)")
                self.child.prompt()
                m = re.match("ret=\$\? && echo \$ret && \(exit \$ret\).*(\d)", self.child.before, flags=re.DOTALL)
                if m:
                    return int(m.group(1))
                else:
                    print_t("Did not match return value regex: '%s', bug?!" % self.child.before, color="red")
                    return None
            except OSError as o:
                print_t("OSError: %s" % o, color="red")
                if sys.stdout.print_exceptions:
                    traceback.print_exc()
            except pexpect.EOF:
                print_t("pexpect.EOF in get_last_return_value()", color="red")
                if sys.stdout.print_exceptions:
                    traceback.print_exc()
        total_time = 0
        running_command_index = 0
        while True:
            index = 0
            try:
                ret = self.child.prompt(timeout=timeout)
                if ret is False:
                    index = 2
            except pexpect.ExceptionPexpect, e:
                # Reached an unexpected state in read_nonblocking()
                # End of File (EOF) in read_nonblocking(). Very pokey platform
                if sys.stdout.print_exceptions:
                    traceback.print_exc()
                break
            except pexpect.EOF, e:
                print_t("pexpect.EOF:", color="red")
                if sys.stdout.print_exceptions:
                    traceback.print_exc()
            except select.error, e:
                # (9, 'Bad file descriptor')
                pass
            except Exception, e:
                index = None
                print_t("Exception (%s): %s" % (str(type(e)), str(e)), color="red")
                traceback.print_exc()
            # Timeout
            if index == 2:
                total_time += timeout
                # This means the command timeout has expanded. Exit
                if command["command_timeout"] and total_time >= command["command_timeout"]:
                    # Send SIGINT to stop command
                    self.child.sendintr()
                    self.command_timed_out = True
                    print_t("Command stopped by timeout '%d', '%s'" %
                            (timeout, self.last_command), color="yellow", verbose=1)
                elif command["commands_while_running"]:
                    cmd = command["commands_while_running"][running_command_index]["cmd"]
                    timeout = command["commands_while_running"][running_command_index]["wait_seconds"]
                    print_t("Sending command line: %s" % cmd, verbose=4)
                    self.child.sendline(cmd)
                    running_command_index += 1
                    running_command_index = running_command_index % len(command["commands_while_running"])
                else:
                    print_t("Default timeout exceeded: %d" % timeout, verbose=4)
            else:
                # Command finished and prompt was read
                break
        if not self.killed and not self.command_timed_out:
            # If error string exists, check for this
            if "error_string" in command:
                if self.child.before.find(command["error_string"]) != -1:
                    return -1
            return get_last_return_value()
        return None

    def handle_commands_executed(self):

        if not self.killed:
            try:
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
            # if self.child.exitstatus != 130:
            #     print_t("Command aborted but exitstatus is not 130: '%s' !?" % (str(self.child.exitstatus)), color="red")
            #     print_t("self.killed:", self.killed)

            should_be_killed = self.conf.get("kill", False)
            if not should_be_killed:
                if sigint_ctrl:
                    print_t("Command on '%-15s' was killed by the script. (Session aborted with CTRL-c by user) "
                            "(Status: %s)\nCommand: '%s'" %
                            (self.host_and_id, str(self.child.exitstatus), self.last_command), color='yellow',
                            split_newlines=True)
                elif global_timeout_expired:
                    print_t("Command on '%-15s' was killed by the script because the global timeout expired (%d). "
                            "(Status: %s)\nCommand: '%s'" %
                            (self.host_and_id, global_timeout_expired, str(self.child.exitstatus), self.last_command),
                            color='yellow', split_newlines=True)
                else:
                    print_t("Command on '%-15s' was killed by the script, but that is not as expected. "
                            "(Status: %s)\nCommand: '%s' " %
                            (self.host_and_id, str(self.child.exitstatus), self.last_command), color='red',
                            split_newlines=True)
            else:
                print_t("Command on '%-15s' was killed by the script. (Status: %s)\nCommand: '%s'" %
                        (self.host_and_id, str(self.child.exitstatus), self.last_command), color='yellow', verbose=1,
                        split_newlines=True)

    def ssh_login(self, user, host):
        if settings["simulate"]:
            return None

        child = pxssh(timeout=30, logfile=self.logfile)
        count = 0
        while True:
            try:
                print_t("Connecting to '%s@%s'" % (self.user, self.host), verbose=3)
                count += 1
                child.login(self.host, self.user, None)
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


def abort_job(results=False, fatal=False):
    global stopped, fatal_abort, gather_results
    stopped = True
    fatal_abort = True if fatal else fatal_abort
    if results is False:
        gather_results = False
    print_t("Job aborted: fatal_abort: %s, gather_results: %s" % (fatal_abort, gather_results))
    print_t("Jobs to kill: %s" % (len(threads) + len(threads_to_kill)), color='red' if not results else None)
    print_t("Threads to kill: %s" % (["".join(t.name_and_host) for t in threads_to_kill + threads]), verbose=3)
    kill_threads(threads)
    kill_threads(threads_to_kill)


def kill_threads(threads_list):
    for t in list(threads_list):
        try:
            if hasattr(t, 'child') and t.child is not None and t.child.isalive():
                t.child.read_nonblocking(size=1000, timeout=0)
        except (pexpect.TIMEOUT, pexpect.EOF) as e:
            # print_t("Exception: when reading nonblocking on child  %s : %s" % (type(e), e))
            # pexpect.TIMEOUT raised if no new data in buffer
            # pexpect.EOF raised when it reads EOF
            pass
        except select.error:
            # (9, 'Bad file descriptor')
            pass
        except OSError as e:
            print_t("kill_threads() Caught OSError:", e, verbose=1)
            if sys.stdout.verbose:
                traceback.print_exc()
        except IOError:
            print_t("kill_threads() Caught IOError:", e, verbose=1)
        except ValueError as e:
            print_t("kill_threads() Caught ValueError:", e)
            traceback.print_exc()
        except Exception as e:
            print_t("kill_threads() Caught Exception:", e)
            traceback.print_exc()
        print_t("Killing thread '%s' running on '%s' command: %s" % (t.name_and_host, t.host, str(t.last_command)),
                verbose=2)

        # Kills the pexpect child
        t.kill()
        # threads_list.remove(t)


def join_current_threads(timeout=None):
    global threads
    ret = join_threads(threads, timeout=timeout)
    threads = []
    return ret


def join_threads(threads, timeout=None):
    print_t("Joining with threads (%d): with timeout: %s %s" % (len(threads), str(timeout),
                                                                str([t.name_and_host for t in threads])), verbose=1)
    start_time = time.time()

    for t in threads:
        print_t("Join thread:", t.name_and_host, verbose=3)
        while True:
            try:
                # Thread hasn't been started yet
                if t.ident is None:
                    time.sleep(1)
                else:
                    t.join(1)
                    if not t.isAlive():
                        break
            except KeyboardInterrupt:
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
            print_t("THREAD IS STILL ALIVE:", t.name_and_host)
    return True

makedirs = []


def setup_directories(args, settings):
    global makedirs
    # Setup directories for storing results and log files
    job_date = datetime.now().strftime("%Y-%m-%d-%H%M-%S")
    jobname_dir = "%s/%s" % (settings["results_dir"], settings["session_name"])
    if args.name:
        settings["resume"] = True
        jobname_dir = "%s/%s" % (jobname_dir, args.name)
        settings["resume_results_dir"] = "%s/all_results" % (jobname_dir)
        makedirs.append(settings["resume_results_dir"])
    settings["results_dir"] = "%s/%s" % (jobname_dir, job_date)
    settings["log_dir"] = "%s/logs" % settings["results_dir"]
    settings["last_dir"] = "%s/last" % jobname_dir
    settings["last_log_dir"] = "%s/log" % settings["last_dir"]
    settings["jobname_dir"] = jobname_dir
    makedirs.append(settings["log_dir"])
    makedirs.append(settings["last_log_dir"])


def mkdirs():
    for d in makedirs:
        try:
            os.makedirs(d)
        except:
            pass


def run_session_job(session_job_conf, jobs, cleanup_jobs, scp_jobs, resume=False):
    global stopped, threads, threads_to_kill, sigint_ctrl, gather_results
    session_job_start_time = datetime.now()

    if session_job_conf:
        print_t("\nStarting session job %d of %d at %s%s\n"
                "ID: %s\n"
                "Description: %s\n"
                "Timeout: %s" % (session_job_conf.get("job_index", [0])[0],
                                 session_job_conf.get("job_index", [0, 0])[1],
                                 str(session_job_start_time),
                                 " (Test mode)" if settings["simulate"] else "",
                                 session_job_conf["name_id"],
                                 session_job_conf["description"],
                                 session_job_conf["timeout_secs"]),
                color='yellow' if settings["simulate"] else 'green', split_newlines=True)

    def do_host_job(job):
        job[0]["log_dir"] = settings["last_log_dir"]
        job[0]["last_dir"] = settings["last_dir"]

        # Prefix logfile name with session job name_id
        if "logfile" in job[0]:
            job[0]["logfile_name"] = job[0]["logfile"]

        t = Job(job[0], session_job_conf, job[1])
        if job[0].get("kill", False):
            threads_to_kill.append(t)
        elif not job[0]["wait"]:
            threads.append(t)
        t.start()
        # We must wait on this job immediately before continuing
        if job[0]["wait"]:
            join_threads([t])

    for i in range(len(jobs)):
        if stopped or fatal_abort:
            break
        job = jobs[i]

        if "host" in job[0]:
            do_host_job(job)
        elif "wait" in job[0]:  # This is for waiting for the commands up to this point
            timeout = None
            if session_job_conf:
                timeout = session_job_conf["timeout_secs"]
                print_t("Waiting for jobs with timeout: %s" %
                        str(session_job_conf["timeout_secs"]), color='green', verbose=1)
            else:
                print_t("Waiting for jobs", color='green', verbose=1)

            # Wait for all previous jobs before continuing
            if join_current_threads(timeout=timeout):
                # Job was not aborted by SIGTERM. Kill the jobs denoted with kill
                print_t("Jobs completed uninterupted. Killing threads: %d" % len(threads_to_kill), color='green')
                # Sleep the number of seconds given in conf
                if job[0]["sleep"]:
                    print_t("Sleeping: %s" % job[0]["sleep"], verbose=3)
                    if not settings["simulate"]:
                        time.sleep(float(job[0]["sleep"]))
                stopped = True
                if not sigint_ctrl:
                    kill_threads(threads_to_kill)
                break
            else:
                # Shouldn't reach this code any longer
                print_t("Test interrupted by CTRL-c!", color='red')
                sigint_ctrl = True
                abort_job()
                break
        elif "sleep" in job[0]:
            print_t("Sleeping: %s" % job[0]["sleep"], verbose=3)
            if not settings["simulate"]:
                time.sleep(float(job[0]["sleep"]))
        elif "gather_results" in job[0]:
            if not (sigint_ctrl or fatal_abort):
                gather_results = job[0]["gather_results"]

    end_time = datetime.now()

    # Do cleanup jobs (defined by cleanup attribute in host conf)
    if cleanup_jobs:
        print_t("Running cleanup jobs...", color="green", verbose=1)
        threads = []
        stopped = False
        for job in cleanup_jobs:
            if not (job[0]["type"] == "ssh" and job[0]["cleanup"]):
                break
            do_host_job(job)

    if scp_jobs:
        if not gather_results:
            print_t("Session job was aborted before being started. No results gathered", color="yellow")
        else:
            # Gather results
            if session_job_conf:
                print_t("Session job '%s' has finished." % session_job_conf["name_id"], color='green')

            print_t("Saving files to: %s" % settings["results_dir"], color="green")
            threads = []
            stopped = False
            for job in scp_jobs:
                # We only want the scp jobs here
                if not job[0]["type"] == "scp":
                    continue

                # Prefix logfile name with session job name_id
                if "logfile" in job[0]:
                    job[0]["logfile_name"] = job[0]["logfile"]

                conf = job[0]
                conf["log_dir"] = settings["last_log_dir"]

                target_filename = conf["target_filename"]
                # Prefix name with session job name_id
                if session_job_conf and session_job_conf["name_id"]:
                    target_filename = "%s_%s" % (session_job_conf["name_id"], target_filename)

                target_file = "%s/%s" % (settings["results_dir"], target_filename)
                link_file = "%s/%s" % (settings["last_dir"], target_filename)
                host, user = get_host_and_user(conf["remote_host"], conf["user"])
                scp_cmd = "scp %s@%s:%s %s" % (user, host, conf["filename"], target_file)

                ln_cmd = "ln -f %s %s" % (target_file, link_file)

                cmd_scp_dict = copy.deepcopy(default_command_conf)
                cmd_ln_dict = copy.deepcopy(default_command_conf)
                cmd_scp_dict["command"] = scp_cmd
                cmd_ln_dict["command"] = ln_cmd
                cmd_scp_dict["return_values"].update(conf["return_values"])
                cmd_ln_dict["return_values"].update(conf["return_values"])
                commands = [cmd_scp_dict, cmd_ln_dict]
                if resume:
                    link_file = "%s/%s" % (settings["resume_results_dir"], target_filename)
                    ln_cmd = "ln -f %s %s" % (target_file, link_file)
                    cmd_ln_dict = copy.deepcopy(default_command_conf)
                    cmd_ln_dict["command"] = ln_cmd
                    cmd_ln_dict["return_values"].update(conf["return_values"])
                    commands.append(cmd_ln_dict)

                t = Job(job[0], session_job_conf, commands)
                threads.append(t)
                t.start()

            if not join_current_threads():
                print_t("Last join interrupted by CTRL-c")

    if session_job_conf:
        line = "Execution of session job '%s'\nfinished in %s at %s" % (session_job_conf["name_id"],
                                                                        str((end_time - session_job_start_time)),
                                                                        str(end_time))
        width = longest_line_width(line)
        print_t("=" * width, color='blue')
        print_t(line, color='blue', split_newlines=True)
        print_t("Results are stored in %s" % settings["results_dir"], color='blue', split_newlines=True)
        print_t("=" * width, color='blue')

    # Copy logs to proper directory
    cmd = "cp %s/*.log %s/" % (settings["last_log_dir"], settings["log_dir"])
    os.popen(cmd).read()

    print_t("Waiting for jobs to kill", verbose=1)
    join_threads(threads_to_kill)
    threads_to_kill = []


def longest_line_width(text):
    length = 0
    for l in text.splitlines():
        if len(l) > length:
            length = len(l)
    return length


def get_host_and_user(host, user):
    m = re.match("((?P<user>.*)@)?(?P<hostname>.+)", host)
    if m:
        if m.group("user"):
            user = m.group("user")
        host = m.group("hostname")
    return host, user


def parse_job_conf(filename, custom_session_settings=None, custom_settings=None):
    global settings
    jobs = []
    cleanup_jobs = []
    scp_jobs = []
    job = None
    f = open(filename, 'r')
    lines = f.readlines()
    f.close()
    eval_lines = ""
    eval_lines_start = 0
    session_jobs = None

    def handle_session_job():
        name_ids = []
        for sj in session_jobs["session_jobs"]:
            if "timeout_secs" not in sj:
                sj["timeout_secs"] = session_jobs["default_session_job_timeout_secs"]
            if "substitutions" not in sj:
                continue

            if sj["name_id"] in name_ids:
                print_t("Duplicate name_id in session_jobs list: %s" % sj["name_id"], color="red")
                print_t("The name_id attribute must be unique for each session job!", color="red")
                raise Exception("Duplicate name_id in session_jobs list: %s" % sj["name_id"])
            else:
                name_ids.append(sj["name_id"])

            for sub in sj["substitutions"].keys():
                # If it refers to default settings, add these to the settings dict
                if session_jobs["default_settings"]:
                    # Exists on both default settings and sub
                    if sub in session_jobs["default_settings"]:
                        sub_settings = copy.deepcopy(session_jobs["default_settings"][sub])
                        sub_settings.update(sj["substitutions"][sub])
                        sj["substitutions"][sub] = sub_settings

                    diff = set(session_jobs["default_settings"].keys()) - set(sj["substitutions"].keys())
                    for key in diff:
                        # Only in default settings, so add to sub
                        sj["substitutions"][key] = session_jobs["default_settings"][key]

    if custom_session_settings is not None:
        session_jobs = default_session_jobs_conf.copy()
        session_jobs.update(custom_session_settings)

    if custom_settings is not None:
        settings.update(custom_settings)

    for i in range(len(lines)):
        # Remove content after #
        line = lines[i]
        if line.find('#') != -1:
            line = line.split("#")[0]
        if not line.strip():
            continue
        try:
            eval_lines += line
            d = eval(eval_lines)
        except Exception, e:
            # Failed ot parse, append next line and try again
            # print_t("Failed to parse:", eval_lines)
            continue
        else:
            eval_lines = ""
            eval_lines_start = i

        # The settings dict
        if "settings" in d:
            settings.update(d)
            if custom_settings is not None:
                settings.update(custom_settings)
            if "session_name" not in settings:
                settings["session_name"] = os.path.splitext(filename)[0]
            if settings["default_user"] is None:
                settings["default_user"] = os.getenv('USER')

        elif "gather_results" in d:
            jobs.append([d])
            job = None
        # New host
        elif "host" in d:
            job_conf = copy.deepcopy(default_job_conf)
            job_conf.update(d)
            job = [job_conf, []]
            host, h_user = get_host_and_user(job_conf["host"], None)
            if h_user:
                if job_conf["user"] and h_user != job_conf["user"]:
                    print_t("User defined both in host string and in user key. host: '%s', user: '%s'. Using user '%s'"
                            % (job_conf["host"], job_conf["user"], job_conf["user"]), color="Magenta")
                else:
                    job_conf["user"] = h_user

            if job_conf["user"] is None:
                job_conf["user"] = settings["default_user"]

            if "ssh" in job_conf:
                job_conf["type"] = "ssh"
            elif "scp" in job_conf:
                job_conf["type"] = "scp"

            if "sigint_before_exit" in job_conf:
                # Default to sending signal once
                if "count" not in job_conf["sigint_before_exit"]:
                    job_conf["sigint_before_exit"]["count"] = 1
                # Default to sleeping 1 second after signal
                if "sleep" not in job_conf["sigint_before_exit"]:
                    job_conf["sigint_before_exit"]["sleep"] = 1

            if job_conf["cleanup"]:
                job_conf["wait"] = True
                cleanup_jobs.append(job)
            elif job_conf["type"] == "scp":
                scp_jobs.append(job)
            else:
                jobs.append(job)

        # Command for host
        elif "command" in d:
            def make_command():
                cmd_conf = copy.deepcopy(default_command_conf)
                cmd_conf.update(d)
                if "print_output" not in d:
                    cmd_conf["print_output"] = job[0]["print_output"]
                if "return_values" in d:
                    cmd_conf["return_values"] = default_command_conf["return_values"].copy()
                    cmd_conf["return_values"].update(d["return_values"])
                else:
                    cmd_conf["return_values"] = job[0]["return_values"].copy()

                # If no 'command_timeout' in command dict, use default from host dict
                if "command_timeout" not in d:
                    cmd_conf["command_timeout"] = job[0]["command_timeout"]
                return cmd_conf
            cmd_conf = make_command()
            # Add the command to the last job conf
            job[1].append(cmd_conf)

        # Do a sleep or wait for all previous jobs
        elif "sleep" in d or "wait" in d:
            conf = copy.deepcopy(default_wait_sleep_conf)
            conf.update(d)
            jobs.append([conf])
            job = None
        elif "session_jobs" in d:
            if session_jobs is None:
                session_jobs = default_session_jobs_conf.copy()
                print("netem_delay1: '%s'" % session_jobs["default_settings"])
                session_jobs.update(d)
                print("netem_delay2: '%s'" % session_jobs["default_settings"]["netem_delay"])
                handle_session_job()

    if eval_lines:
        print_t("You have a syntax error in the job config (around line %d)!" % (eval_lines_start), color="red")
        # print_t("Failed to parse config lines: %s" % eval_lines, color="red")
        import parser
        e = parser.expr(eval_lines)
        parser.compilest(e)
        sys.exit(0)

    if session_jobs:
        handle_session_job()

    # Add last job
    if job is not None:
        jobs.append(job)

    # handle "foreach" in host config, have to make a copy for each job config for each value
    new_jobs = []
    for j in jobs:
        if not j[0].get("foreach", False):
            # Nothing to do, so add to list
            new_jobs.append(j)
        else:
            # Hack, just use the subsitute_ids of the first job
            sj = session_jobs["session_jobs"][0]
            for s_id in sj["substitutions"][j[0]["substitute_id"]]["foreach"]:
                new_job = copy.deepcopy(j)
                for k in new_job[0]:
                    # Ignore of not string
                    if type(new_job[0][k]) is not str:
                        continue
                    new_job[0][k] = new_job[0][k] % sj["substitutions"][s_id]
                new_jobs.append(new_job)

    jobs = new_jobs
    return settings, session_jobs, jobs, cleanup_jobs, scp_jobs


def to_bool(value):
    """
       Converts 'something' to boolean. Raises exception for invalid formats
           Possible True  values: 1, True, "1", "TRue", "yes", "y", "t"
           Possible False values: 0, False, None, [], {}, "", "0", "faLse", "no", "n", "f", 0.0, ...
    """
    if str(value).lower() in ("yes", "y", "true", "t", "1"):
        return True
    if str(value).lower() in ("no", "n", "false", "f", "0"):
        return False
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
        global signal_handler_running

        if signal_handler_running is True:
            print_t("Signal handler already running")
            return
        signal_handler_running = True
        sigint_ctrl = True
        print_t("Session interrupted by SIGINT signal. Killing threads...", color="red")
        try:
            abort_job(fatal=True, results=settings["gather_results_on_cancel"])
        except Exception, e:
            print_t("signal_handler - Caught Exception (%s): %s!" % (str(type(e)), str(e)), color="red")
        except:
            print_t("signal_handler - Caught unspecified error!", color="red")
            pass
        for i, h in enumerate(SignalHandler.active_handlers):
            if self is h:
                del SignalHandler.active_handlers[i]

        print_t("LockFileHandler running:", lockFileHandler.running, verbose=1)
        print_t("Threads         (%d): %s" % (len(threads), str(threads)), verbose=1)
        print_t("Threads to kill (%d): %s" % (len(threads_to_kill), str(threads_to_kill)), verbose=1)
        print_t("SignalHandler run finished.", verbose=3)
        signal_handler_running = False


class LockFileHandler(Thread):

    def __init__(self, lock_file, force):
        self.lock_file = lock_file
        self.running = True
        self.wait_cond = threading.Condition()
        self.update_interval = 60
        self.name_and_host = "LockFileHandler"

        lock_file_content = self.get_lcokfile_content()
        if lock_file_content:
            if force:
                # os.remove(lock_file)
                pass
            else:
                diff = time.time() - os.path.getmtime(lock_file)

                # Changed less than self.update_interval ago
                if diff < self.update_interval * 2:
                    print_t("Lock file is present (%s) and was updated %d seconds ago." %
                            (lock_file, int(diff)), color="red")
                    print_t("Either a job is currently running, or a lock file from a recent "
                            "failed session was not correctly removed.", color="red")
                    f = open(lock_file, "r")
                    print("Lock file content:\n", f.read())
                    f.close()
                    sys.exit()

        Thread.__init__(self)
        self.daemon = True
        # Create new lockfile
        f = open(lock_file, 'w+')
        date = datetime.now().strftime("%Y-%m-%d-%H%M-%S")
        f.write("Test name: %s\n" % settings["session_name"])
        f.write("Started at: %s\n" % date)
        f.close()
        self.start()
        return None

    def get_lcokfile_content(self):
        if os.path.isfile(self.lock_file):
            f = open(self.lock_file, 'r')
            content = f.read()
            f.close()
            return content
        else:
            return None

    def stop(self):
        self.running = False
        self.wait_cond.acquire()
        self.wait_cond.notify()
        self.wait_cond.release()
        # Join with the LockFileHandler thread
        join_threads([self], timeout=None)
        os.remove(self.lock_file)

    def run(self):
        while self.running:
            self.wait_cond.acquire()
            self.wait_cond.wait(self.update_interval)
            self.wait_cond.release()
            os.utime(self.lock_file, None)
        print_t("LockFileHandler run finished.", verbose=3)


def write_info_file(args, session_info_to_file):
    filename = "info.nfo"
    filepath = os.path.join(settings["results_dir"], filename)
    print_t("Writing INFO FILE: %s" % filepath, verbose=1)
    f = open(filepath, "w")
    f.write("session start time: %s\n" % str(session_start_time))
    f.write("session end time: %s\n" % str(session_end_time))

    d = datetime(1, 1, 1) + (session_end_time - session_start_time)
    f.write("Total duration: %d:%d:%d:%d\n" % (d.day - 1, d.hour, d.minute, d.second))
    if session_info_to_file:
        f.write("Session info:\n%s\n" % session_info_to_file)
    f.close()
    os.link(os.path.abspath(filepath), os.path.join(settings["last_dir"], filename))


def parse_args(argparser=None):
    if argparser is None:
        argparser = argparse.ArgumentParser(description="Run test sessions")
    argparser.add_argument("-v", "--verbose", help="Enable verbose output. Can be applied multiple times (Max 3)",
                           action='count', default=0, required=False)
    argparser.add_argument("-x", "--exceptions", help="Print full exception traces", action='store_true',
                           required=False, default=False)
    argparser.add_argument("-s", "--simulate", help="Simulate only, do not execute commands.",
                           action='store_true', required=False)
    argparser.add_argument("-c", "--print-commands", help="Print the shell commands being executed.",
                           action='store_true', required=False)
    argparser.add_argument("-pco", "--print-command-output", metavar='boolean string',
                           help="Print the output from all the remote commands to stdout."
                           "This overrides any settings in the config file.", required=False)
    argparser.add_argument("-nto", "--no-terminal-output", action='store_true', help="Do not print anything to terminal"
                           ". The terminal output will only be written to terminal.log", required=False, default=False)
    argparser.add_argument("-n", "--name", help="The name of this session. A directory named 'name' will be created "
                           "for the results.", required=False, default=None)
    argparser.add_argument("-r", "--resume", help="Resume the last session job. Requires --name argument.",
                           required=False, action='store_true', default=False)
    argparser.add_argument("-f", "--force", help="Ignores any existing lock file forcing the session to run.",
                           action='store_true', required=False, default=False)
    argparser.add_argument("config_file", help="The configuration file with the commands to run.")
    args = argparser.parse_args()
    return args


def setup(args, custom_session_settings=None, custom_settings=None):
    global session_start_time, lockFileHandler
    global print_commands, print_command_output, no_terminal_output
    check_pexpect_version()
    signal_handler = SignalHandler()
    signal.signal(signal.SIGINT, signal_handler.handle_signal)

    sys.stdout.verbose = args.verbose
    sys.stdout.print_exceptions = args.exceptions
    lockFileHandler = LockFileHandler(lock_file, args.force)

    if args.no_terminal_output:
        no_terminal_output = True

    if args.print_command_output:
        print_command_output = to_bool(args.print_command_output)

    settings, session_jobs, jobs, cleanup_jobs, scp_jobs = parse_job_conf(args.config_file,
                                                                          custom_session_settings=custom_session_settings,
                                                                          custom_settings=custom_settings)
    if args.simulate:
        settings["simulate"] = True

    if args.print_commands:
        print_commands = True

    setup_directories(args, settings)
    return settings, session_jobs, jobs, cleanup_jobs, scp_jobs


def run_jobs(settings, session_jobs, jobs, cleanup_jobs, scp_jobs, args, session_info_to_file=None):
    global session_start_time, session_end_time, stopped, global_timeout_expired
    global retry_session_job
    session_start_time = datetime.now()
    print_t("Starting session '%s' at %s %s" % (settings["session_name"], str(session_start_time),
                                                "in test mode" if settings["simulate"] else ""),
            color='yellow' if settings["simulate"] else 'green')

    # session_jobs defined in config
    if session_jobs:
        print_t("Session jobs to run: %d" % len(session_jobs["session_jobs"]))
        i = 0
        while i < len(session_jobs["session_jobs"]):
            if fatal_abort or sigint_ctrl:
                break
            session_job = session_jobs["session_jobs"][i]
            stopped = False
            global_timeout_expired = 0
            if i != 0 and session_jobs["delay_between_session_jobs_secs"]:
                print_t("Sleeping %d seconds before next session job." %
                        session_jobs["delay_between_session_jobs_secs"])
                if not settings["simulate"]:
                    time.sleep(session_jobs["delay_between_session_jobs_secs"])
            run_session_job(session_job, jobs, cleanup_jobs, scp_jobs, resume=settings["resume"])
            if retry_session_job:
                retry_session_job = False
                i = i - 1
                print_t("Retrying session job '%s'" % session_jobs["session_jobs"][i]["name_id"], color="yellow")
            i += 1
    else:
        run_session_job(None, jobs, cleanup_jobs, scp_jobs, resume=settings["resume"])

    if sigint_ctrl:
        print_t("Session stopped by SIGINT signal")

    if fatal_abort:
        print_t("\nSession was aborted!", color="red")

    session_end_time = datetime.now()
    print_t("\n")
    color = "blue"
    if fatal_abort:
        color = "red"
    line = "Execution of session '%s' finished in %s seconds at %s" % (settings["session_name"],
                                                                       str((session_end_time - session_start_time)),
                                                                       str(session_end_time))
    print_t("*" * len(line), color=color)
    print_t("*" * len(line), color=color)
    print_t(line, color=color)
    print_t("*" * len(line), color=color)
    print_t("*" * len(line), color=color)

    # Write results file
    write_info_file(args, session_info_to_file)


def do_run_jobs(settings, session_jobs, jobs, cleanup_jobs, scp_jobs, args, session_info_to_file=None):
    try:
        mkdirs()
        # Delete all the leftover files in last and last log dir
        cmd = "rm -f %s/*.* %s/*.*" % (settings["last_dir"], settings["last_log_dir"])
        os.popen(cmd).read()
        # Setting log file for the terminal output
        sys.stdout.output_file = open(os.path.join(settings["last_log_dir"], "terminal.log"), 'w+')
    except:
        print_t("Exception in main: %s" % threading.current_thread().name)
        traceback.print_exc()

    try:
        run_jobs(settings, session_jobs, jobs, cleanup_jobs, scp_jobs, args, session_info_to_file)
    except SystemExit:
        pass
    except:
        print_t("Exception in main: %s" % threading.current_thread().name)
        traceback.print_exc()
        try:
            kill_threads(threads)
            kill_threads(threads_to_kill)
        except:
            print_t("Exception in main: %s" % threading.current_thread().name)
            traceback.print_exc()
            os._exit(1)
    finally:
        if lockFileHandler:
            lockFileHandler.stop()
        sys.stdout.close()


def main():
    args = parse_args()
    settings, session_jobs, jobs, cleanup_jobs, scp_jobs = setup(args)
    do_run_jobs(settings, session_jobs, jobs, cleanup_jobs, scp_jobs, args)


if __name__ == "__main__":
    main()
