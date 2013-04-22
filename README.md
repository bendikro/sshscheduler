sshscheduler
============

sshscheduler is a python script that executes commands on hosts over ssh.

The jobs to execute are defined in a text file as python dictionaries.

Very simple example:

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

