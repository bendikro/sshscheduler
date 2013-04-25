.. sshscheduler documentation master file, created by
   sphinx-quickstart on Thu Apr 25 13:29:39 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to sshscheduler's documentation!
========================================

The sshscheduler session configuration is defined in a text file using python dictionaries.

.. toctree::
   :maxdepth: 2

Config dictionaries
====================

The following dictionaries can be defined in the config:

.. py:function:: settings(settings, results_dir="results", session_name="sshscheduler_example_session", simulate=False, default_user=os.getenv('USER'))

    The settings config is mandatory

    :param settings: Defines the settings
    :type settings: ignored
    :param results_dir: The base directory where the results are stored
    :type results_dir: string
    :param session_name: The name of the session
    :type session_name: string
    :param simulate: If the session jobs should just be simulated
    :type simulate: bool
    :param default_user: The default user to use for the remote hosts
    :type default_user: string

.. py:function:: session_jobs(session_jobs, delay_between_session_jobs_secs=0, default_session_job_timeout_secs=None, default_settings=None)

    :param session_jobs: the session jobs to run
    :type session_jobs: dict
    :param delay_between_session_jobs_secs: Number of seconds to wait between each session job execution
    :type delay_between_session_jobs_secs: int
    :param default_session_job_timeout_secs: The global timeout for each session job in seconds
    :type default_session_job_timeout_secs: int
    :param default_settings: The default settings to use for a session job
    :type default_settings: dict

.. py:function:: ssh(type, host, logfile, kill=False, user=None, print_output=False)

    :param type: "ssh"
    :type type: string
    :param host: The hostname to connect to
    :type host: string
    :param logfile: The name of the log file for this job
    :type logfile: string
    :param type: The type of job
    :type type: string ssh/scp
    :param kill: If this job is expected to finish or if it should be killed
    :type kill: bool
    :param user: The remote user to connect to
    :type user: string
    :param print_output: If the output from the commands run on this host should be printed to terminal
    :type print_output: bool

.. py:function:: command(command, substitute_id=None, command_timeout=None, return_values={"pass": [0]})

    :param command: The command to execute on the previously defined ssh job
    :type command: string
    :param substitute_id: The id of the substitution dictionary to be used for this command.
    :type substitute_id: string
    :param command_timeout: The timeout for this command in seconds
    :type command_timeout: int
    :param return_values: The values to accept for either passing or failing exit value
    :type return_values: dict pass/fail
    :param print_output: If the output from the commands run on this host should be printed to terminal
    :type print_output: bool

.. py:function:: scp(type, host, remote_host, filename, target_filename, logfile, user=None, print_output=False)

    :param type: "scp"
    :type type: string
    :param host: The hostname to connect to
    :type host: string
    :param remote_host: The host to copy files from
    :type remote_host: string
    :param filename: The filename to copy
    :type filename: string
    :param target_filename: The filename to save as
    :type target_filename: string
    :param logfile: The name of the log file for this job
    :type logfile: string
    :param user: The remote user to connect to
    :type user: string

.. py:function:: gather_results(gather_results)

    :param gather_results: To gather results if the session job execuiton ends here (e.g. after being interrupted by CTRL-c)
    :type gather_results: bool

.. py:function:: sleep(sleep)

    :param sleep: The number of seconds to sleep before continuing
    :type sleep: int

.. py:function:: wait(wait, sleep=0)

    :param wait: Wait at this point on all hosts not defined with kill=True
    :type wait: string
    :param sleep: The number of seconds to sleep after the jobs that were waited for have finished.
    :type sleep: int


Config Examples
==================

Simple example:
-------------------

.. code-block:: python

    {"settings": "", "results_dir": "results", # Root dir of where to save files copied with scp and log files
     "session_name": "example_session",
     "simulate": False, # Simulate will not execute the commands
     "default_user": None
    }

    {"host" : "localhost", "logfile" : "localhost_commands.log", "type" : "ssh" }
    {"command" : "ls -l" }
    {"command" : 'echo "Test1" > result.txt' }
    {"command" : 'echo "Test2" > result2.txt' }
    
    # Wait for jobs (threads) to finish
    {"wait" : ""}
    
    # Copy remote files files
    {"type" : "scp", "host" : "localhost", "remote_host" : "localhost", "filename": "result.txt",  "target_filename": "result.txt",  "logfile" : "localhost_scp1.log" }
    {"type" : "scp", "host" : "localhost", "remote_host" : "localhost", "filename": "result2.txt", "target_filename": "result2.txt", "logfile" : "localhost_scp2.log" }


Bigger Example
-------------------

.. literalinclude:: example_job.txt
   :language: python


Biggest Example
-------------------

.. literalinclude:: example_job_advanced.txt
   :language: python
