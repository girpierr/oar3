# -*- coding: utf-8 -*-
import re
import sys
import os
import socket
import signal
import click
from pwd import getpwnam
from pathlib import Path

from .utils import CommandReturns

click.disable_unicode_literals_warning = True

from oar.lib import config

from oar.lib import (db, Job)

from oar.lib.submission import (JobParameters, Submission, lstrip_none,
                                check_reservation, default_submission_config)

from oar.lib.job_handling import (get_job, get_job_types, get_job_current_hostnames,
                                  get_job_cpuset_name, get_current_moldable_job)

from oar.lib.tools import (DEFAULT_CONFIG, get_oarexecuser_script_for_oarsub)

import oar.lib.tools as tools



def init_tcp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((socket.getfqdn(), 0))
    sock.listen(5)
    return sock


def qdel(signal, frame):
    '''To address ^C in interactive submission.'''
    # TODO launch a qdel
    print('TODO launch a qdel')
    exit
    
#signal.signal(signal.SIGINT, qdel)
#signal.signal(signal.SIGHUP, qdel)
#signal.signal(signal.SIGPIPE, qdel)


def connect_job(job_id, stop_oarexec, openssh_cmd, cmd_ret):
    '''Connect to a job and give the shell of the user on the remote host.'''
    # TODO: Remove stop_oarexec ???
    xauth_path = os.environ['OARXAUTHLOCATION'] if 'OARXAUTHLOCATION' in os.environ else None
    lusr = os.environ['OARDO_USER'] if 'OARDO_USER' in os.environ else None

    job = get_job(job_id)

    if (lusr == job.user) or (luser == 'oar') or (job.state == 'Running'):
        types = get_job_types(job_id)
        #noop
        if 'noop' in types:
            cmd_ret.warning('/!\\ It is not possible to connect to a NOOP job.')
            cmd_ret.exit(17);

        hosts = get_job_current_hostnames(job_id)
        host_to_connect_via_ssh = hosts[0]
        
        #deploy, cosystem and no host part
        if 'cosystem' in types or not hosts:
            host_to_connect_via_ssh = config['COSYSTEM_HOSTNAME']
        elif 'deploy' in types:
            host_to_connect_via_ssh = config['DEPLOY_HOSTNAME']

        #cpuset part
        cpuset_field = config['JOB_RESOURCE_MANAGER_PROPERTY_DB_FIELD']
        cpuset_path = config['CPUSET_PATH']
        
        if cpuset_field and cpuset_path and ('cosystem' not in types) and ('deploy' not in types) and hosts:
            os.environ['OAR_CPUSET'] = cpuset_path +'/' + get_job_cpuset_name(job_id)
        else:
            os.environ['OAR_CPUSET'] = ''

        moldable = get_current_moldable_job(job.assigned_moldable_job)
        job_user = job.user
        shell = getpwnam(lusr).pw_shell

        # TODO
        # unless ((defined($xauth_path)) and (-x $xauth_path) and ($ENV{DISPLAY} =~ /^[\w.-]*:\d+(?:\.\d+)?$/)) {
        #             $ENV{DISPLAY}="";
        #         }
        #         if ($ENV{DISPLAY} ne ""){
        #             print("# Info: Initialize X11 forwarding...\n");
        #             # first, get rid of remaining unused .Xautority.{pid} files...
        #             system({"bash"} "bash","-c",'for f in $HOME/.Xauthority.*; do [ -e "/proc/${f#$HOME/.Xauthority.}" ] || rm -f $f; done');
        #             my $new_xauthority = $ENV{HOME}."/.Xauthority.$$";
        #             system({"bash"} "bash","-c",'[ -x "'.$xauth_path.'" ] && OARDO_BECOME_USER='.$lusr.' oardodo bash --noprofile --norc -c "'.$xauth_path.' extract - ${DISPLAY/#localhost:/:}" | XAUTHORITY='.$new_xauthority.' '.$xauth_path.' -q merge - 2>/dev/null');
        #             $ENV{XAUTHORITY} = $new_xauthority;
        #         }
        
        node_file = config['OAREXEC_DIRECTORY'] + '/' + str(job_id)
        resource_file = node_file + '_resources'
        oarsub_pids = config['OAREXEC_DIRECTORY'] + '/' + config['OARSUB_FILE_NAME_PREFIX'] + str(job_id)

        script = get_oarexecuser_script_for_oarsub(job, moldable.walltime, node_file, shell, resource_file)

        cmd = openssh_cmd
        if ('OAR_CPUSET' in os.environ) and ('OAR_CPUSET' != ''):
            cmd += ' -oSendEnv=OAR_CPUSET '

        if ('DISPLAY' in os.environ) and ('DISPLAY' != ''):
            cmd += ' -X '
        else:
            cmd += ' -x '

        cmd += '-t ' + host_to_connect_via_ssh + ' '
        
        if ('DISPLAY' in os.environ) and ('DISPLAY' != ''):
            # TODO: X display forwarding
            #$cmd[$i] = "bash -c 'echo \$PPID >> $oarsub_pids && ($xauth_path -q extract - \${DISPLAY/#localhost:/:} | OARDO_BECOME_USER=$lusr oardodo $xauth_path merge -) && [ \"$lusr\" != \"$job_user\" ] && OARDO_BECOME_USER=$lusr oardodo bash --noprofile --norc -c \"chmod 660 \\\$HOME/.Xauthority\" ;TTY=\$(tty) && test -e \$TTY && oardodo chown $job_user:oar \$TTY && oardodo chmod 660 \$TTY' && OARDO_BECOME_USER=$job_user oardodo bash --noprofile --norc -c '$str'";$i++;
            raise 'X display forwarding support NOT yet implemented'
        else:
            # No X display forwarding
            cmd += "\"bash -c 'echo \$PPID >> " + oarsub_pids + " && TTY=\$(tty) && test -e \$TTY && oardodo chown "\
                   + job.user + ":oar \$TTY && oardodo chmod 660 \$TTY' && OARDO_BECOME_USER=" + job.user\
                   + " oardodo bash --noprofile --norc -c '" + script + "'\""
        #print('oarsub launchs command : ' + cmd)
        
        # Essential : you become oar instead of the user
        # Set real to effective uid
        os.setuid(os.geteuid()) #TODO: Do really need to do this ?
        
        print("Connect to OAR job " + str(job_id) + ' via the node ' + host_to_connect_via_ssh)
        return_code = tools.run(cmd, shell=True).returncode
        
        exit_value = return_code >> 8
        if exit_value == 2:
            cmd_ret.warning('# Error: cannot enter working directory: ' + job.launching_directory)
        elif exit_value != 0:
            cmd_ret.warning('# Error: an unexpected error: ' + str(return_code))

        if stop_oarexec > 0:
            tools.signal_oarexec(host_to_connect_via_ssh, signal, 0, openssh_cmd)
            cmd_ret.info('Disconnected from OAR job ' + str(job_id))

            
    else:
        if job.state_!= 'Running':
            cmd_ret.error('Job ' + str(job_id) + ' is not running, current state is ' + job.state + '.')
        
        if (lusr != job.user) and (lusr != 'oar'):
            cmd_ret.error('User mismatch for job ' + str(job_id) + ' (job user is ' + job.user + '.')
        cmd_ret.exit(20)

    cmd_ret.exit(0)
    

def resubmit_job(job_id):
    # TODO
    print('TODO resubmit_job')
    return ((-42, "Not yet implemented"), -1)

# Move to oar.lib.tool
def signal_almighty(remote_host, remote_port, msg):
    print('TODO signal_almighty')
    return 1


@click.command()
@click.argument('command', required=False)
@click.option('-I', '--interactive', is_flag=True,
              help='Interactive mode. Give you a shell on the first reserved node.')
@click.option('-q', '--queue', default='default',
              help='Specifies the destination queue. If not defined the job is enqueued in default queue')
@click.option('-l', '--resource', type=click.STRING, multiple=True,
              help="Defines resource list requested for a job: resource=value[,[resource=value]...]\
              Defined resources :\
              nodes : Request number of nodes (special value 'all' is replaced by the number of free\
              nodes corresponding to the weight and properties; special value ``max'' is replaced by\
              the number of free,absent and suspected nodes corresponding to the weight and properties).\
              walltime : Request maximun time. Format is [hour:mn:sec|hour:mn|mn]\
              weight : the weight that you want to reserve on each node")
@click.option('-p', '--property', type=click.STRING,
              help='Specify with SQL syntax reservation properties.')
@click.option('-r', '--reservation', type=click.STRING,
              help='Ask for an advance reservation job on the date in argument.')
@click.option('-C', '--connect', type=int,
              help='Connect to a reservation in Running state.')
@click.option('--array', type=int,
              help="Specify an array job with 'number' subjobs")
@click.option('--array-param-file', type=click.STRING,
              help='Specify an array job on which each subjob will receive one line of the \
              file as parameter')
@click.option('-S', '--scanscript', is_flag=True,
              help='Batch mode only: asks oarsub to scan the given script for OAR directives \
              (#OAR -l ...)')
@click.option('-k', '--checkpoint', type=int, default=0,
              help='Specify the number of seconds before the walltime when OAR will send \
              automatically a SIGUSR2 on the process.')
@click.option('--signal', type=int,
              help='Specify the signal to use when checkpointing Use signal numbers, \
              default is 12 (SIGUSR2)')
@click.option('-t', '--type', type=click.STRING, multiple=True,
              help='Specify a specific type (deploy, besteffort, cosystem, checkpoint, timesharing).')
@click.option('-d', '--directory', type=click.STRING, default=str(Path.home()),
              help='Specify the directory where to launch the command (default is current directory)')
@click.option('--project', type=click.STRING,
              help='Specify a name of a project the job belongs to.')
@click.option('--name', type=click.STRING,
              help='Specify an arbitrary name for the job')
@click.option('-a', '--after', type=click.STRING, multiple=True,
              help='Add a dependency to a given job, with optional min and max relative \
              start time constraints (<job id>[,m[,M]]).')
@click.option('--notify', type=click.STRING,
              help='Specify a notification method (mail or command to execute). Ex: \
              --notify "mail:name\@domain.com"\
              --notify "exec:/path/to/script args"')
@click.option('-k', '--use-job-key', is_flag=True,
              help='Activate the job-key mechanism.')
@click.option('-i', '--import-job-key-from-file', type=click.STRING,
              help='Import the job-key to use from a files instead of generating a new one.')
@click.option('--import-job-key-inline', type=click.STRING,
              help='Import the job-key to use inline instead of generating a new one.')
@click.option('-e', '--export-job-key-to-file', type=click.STRING,
              help='Export the job key to a file. Warning: the\
              file will be overwritten if it already exists.\
              (the %jobid% pattern is automatically replaced)')
@click.option('-O', '--stdout', type=click.STRING,
              help='Specify the file that will store the standart output \
              stream of the job. (the %jobid% pattern is automatically replaced)')
@click.option('-E', '--stderr', type=click.STRING,
              help='Specify the file that will store the standart error stream of the job.')
@click.option('--hold', is_flag=True,
              help='Set the job state into Hold instead of Waiting,\
              so that it is not scheduled (you must run "oarresume" to turn it into the Waiting state)')
@click.option('--resubmit', type=int,
              help='Resubmit the given job as a new one.')
@click.option('-V', '--version', is_flag=True,
              help='Print OAR version number.')
def cli(command, interactive, queue, resource, reservation, connect,
        type, checkpoint, property, resubmit, scanscript, project, signal,
        directory, name, after, notify, array, array_param_file,
        use_job_key, import_job_key_from_file, import_job_key_inline, export_job_key_to_file,
        stdout, stderr, hold, version):
    """Submit a job to OAR batch scheduler."""
    
    #set default config for submission
    default_submission_config(tools.DEFAULT_CONFIG)
    
    #import pdb; pdb.set_trace()
    cmd_ret = CommandReturns()
    
    log_warning = ''  # TODO
    log_error = ''
    log_info = ''
    log_std = ''

    # TODO
    remote_host = config['SERVER_HOSTNAME']
    remote_port = int(config['SERVER_PORT'])

    # TODO Deploy_hostname / Cosystem_hostname
    # $Deploy_hostname = get_conf("DEPLOY_HOSTNAME");
    # if (!defined($Deploy_hostname)){
    #    $Deploy_hostname = $remote_host;
    # }

    # $Cosystem_hostname = get_conf("COSYSTEM_HOSTNAME");
    # if (!defined($Cosystem_hostname)){
    #    $Cosystem_hostname = $remote_host;
    # }

    cpuset_field = config['JOB_RESOURCE_MANAGER_PROPERTY_DB_FIELD']
    cpuset_path = config['CPUSET_PATH']

    if 'OAR_RUNTIME_DIRECTORY' in config:
        pass
    # if (is_conf("OAR_RUNTIME_DIRECTORY")){
    #  OAR::Sub::set_default_oarexec_directory(get_conf("OAR_RUNTIME_DIRECTORY"));
    # }

    # my $default_oar_dir = OAR::Sub::get_default_oarexec_directory();
    # if (!(((-d $default_oar_dir) and (-O $default_oar_dir)) or (mkdir($default_oar_dir)))){
    #    die("# Error: failed to create the OAR directory $default_oar_dir, or bad permissions.\n");
    # }

    binpath = ''
    if 'OARDIR' in os.environ:
        binpath = os.environ['OARDIR'] + '/'
    else:
        cmd_ret.error('OARDIR environment variable is not defined.', 0, 1)
        cmd_ret.exit()

    openssh_cmd = config['OPENSSH_CMD']
    ssh_timeout = int(config['OAR_SSH_CONNECTION_TIMEOUT'])

    # if (is_conf("OAR_SSH_CONNECTION_TIMEOUT")){
    #    OAR::Sub::set_ssh_timeout(get_conf("OAR_SSH_CONNECTION_TIMEOUT"));
    # }

    # OAR version
    # TODO: OAR is now a set of composition...

    # TODO ssh_private_key, ssh_public_key,
    # ssh_private_key = ''
    # ssh_public_key = ''

    # TODO import_job_key_file, export_job_key_file
    import_job_key_file = ''
    export_job_key_file = ''

    if resubmit:
        cmd_ret.print_('# Resubmitting job ' + str(resubmit) + '...')
        error, job_id = resubmit_job(resubmit)
        if error[0] == 0:
            print(' done.\n')
            print('OAR_JOB_ID=' + str(job_id))
            if signal_almighty(remote_host, remote_port, 'Qsub') > 0:
                error_msg = 'cannot connect to executor ' + str(remote_host) + ':' +\
                            str(remote_port) + '. OAR server might be down.'
                cmd_ret.error(error_msg, 0, 3)
                cmd_ret.exit()
            else:
                # It's all good
                cmd_ret.exit()
                
        else:
            cmd_ret.error('TODO', 0, error)
            cmd_ret.exit()
            # TODO
            #print(' error.')
            #if ret == -1:
            #    print_error('interactive jobs and advance reservations cannot be resubmitted.')
            #elif ret == -2:
            #    print_error('only jobs in the Error or Terminated state can be resubmitted.')
            #elif ret == -3:
            #    print_error('resubmitted job user mismatch.')
            #elif ret == -4:
            #    print_error('another active job is using the same job key.')
            #else:
            #    print_error('unknown error.')
            #exit(4)


    # TODO   Connect to a reservation
    # Connect to a reservation
    # if (defined($connect_job)){
    # Do not kill the job if the user close the window
    #  $SIG{HUP} = 'DEFAULT';
    #  OAR::Sub::close_db_connection(); exit(connect_job($connect_job,0,$Openssh_cmd));
    # }
    
    properties = lstrip_none(property)
    types = type
    initial_request = ' '.join(sys.argv[1:])
    queue_name = lstrip_none(queue)    

    reservation_date = check_reservation(lstrip_none(reservation))

    # TODO import_job_key_file, export_job_key_file
    import_job_key_file = ''
    export_job_key_file = ''

    user = os.environ['OARDO_USER']
    
    # TODO verify if all need parameters are identifed and present for submission 
    job_parameters = JobParameters(job_type=None,
                                   resource=resource,
                                   command=command,
                                   info_type=None,
                                   queue=queue_name,
                                   properties=properties,
                                   checkpoint=checkpoint,
                                   signal=signal,
                                   notify=notify,
                                   name=name,
                                   types=types,
                                   directory=directory,
                                   dependencies=after,
                                   stdout=stdout,
                                   stderr=stderr,
                                   hold=hold,
                                   project=project,
                                   initial_request=initial_request,
                                   user=user,
                                   interactive=interactive,
                                   reservation=reservation_date,
                                   connect=connect,
                                   scanscript=scanscript,
                                   array=array,
                                   array_param_file=array_param_file,
                                   use_job_key=use_job_key,
                                   import_job_key_inline=import_job_key_inline,
                                   import_job_key_file=import_job_key_file,
                                   export_job_key_file=export_job_key_file)
    

    #import pdb; pdb.set_trace()

    error = job_parameters.check_parameters()
    if error[0] != 0:
        cmd_ret.error('', 0, error)
        cmd_ret.exit()

    #import pdb; pdb.set_trace()
    submission = Submission(job_parameters)

    # TO REMOVE
    # command, initial_request, interactive, queue, resource,
    # type, checkpoint, property, resubmit, scanscript, project,
    # directory, name, after, notify, array, array_param_
    # export_job_key_to_file, stdout, stderr, hold)

    if not interactive and command:

        cmd_executor = 'Qsub'

        if scanscript:
            # TODO scanscript
            pass

        array_params = []
        if array_param_file:
            pass
        # TODO
        # $array_params_ref = OAR::Sub::read_array_param_file($array_param_file);
        # $array_nb = scalar @{$array_params_ref};

        if job_parameters.array_nb == 0:
            pass
        #    print_error('an array of job must have a number of sub-jobs greater than 0.')
        #    usage()
        #    exit(6)

        job_parameters.info_type = "frontend:" #"$Host:$server_port"  # TODO  "$Host:$server_port"
        job_parameters.job_type = 'PASSIVE'


        (error, job_id_lst) = submission.submit()

    else:
        # TODO interactive
        if command:
            cmd_ret.warning('asking for an interactive job (-I), so ignoring arguments: ' + command + ' .')
        else:
            command = ''
            job_parameters.command = command

        cmd_executor = 'Qsub -I'

        if array_param_file:
            cmd_ret.error('a array job with parameters given in a file cannot be interactive.', 0, 9)
            cmd_ret.exit()
        if job_parameters.array_nb != 1:
            cmd_ret.error('an array job cannot be interactive.', 0, 8)
            cmd_ret.exit()

        if reservation:
            # Test if this job is a reservation and the syntax is right
            # TODO Pass
            pass

        socket_server = init_tcp_server()
        (server, server_port) = socket_server.getsockname()
        
        job_parameters.info_type = server + ':' + str(server_port)
        job_parameters.job_type = 'INTERACTIVE'

        (error, job_id_lst) = submission.submit()

    # pdb.set_trace()

    if error[0] != 0:
        cmd_ret.error('unamed error', 0, error) #TODO
        cmd_ret.exit()

    oar_array_id = 0

    # Print job_id list
    if len(job_id_lst) == 1:
        print('OAR_JOB_ID=', job_id_lst[0])
    else:
        job = db['Job'].query.filter(Job.id == job_id_lst[0]).one()
        oar_array_id = job.array_id
        for job_id in job_id_lst:
            print('OAR_JOB_ID=', job_id)

    result = (job_id_lst, oar_array_id)

    # Notify Almigthy
    tools.create_almighty_socket()
    tools.notify_almighty(cmd_executor)

    if reservation:
        # Reservation mode
        cmd_ret.info("advance reservation request: waiting for approval from the scheduler...")

        (conn, address) = socket_server.accept()
        answer = conn.recv(1024)
        if answer[:-1] == 'GOOD RESERVATION':
            cmd_ret.info('Advance reservation is GRANTED.')
        else:
            cmd_ret.info('Advance reservation is REJECTED ' + answer[:-1], 0, 10)
    elif interactive:
        # Interactive mode
        cmd_ret.info('Interactive mode: waiting...')

        prev_str = ''
        while True:
            (conn, address) = socket_server.accept()
            message = conn.recv(1024)
            message = message[:-1]
            answer = message.decode()

            print(answer)
            
            m = re.search(r'\](.*)$', answer)
            if m and m.group(1) != prev_str:
                cmd_ret.info(answer)
                prev_str = m.group(1)
            elif answer != 'GOOD JOB':
                cmd_ret.info(answer)

            if (answer == 'GOOD JOB') or (answer == 'BAD JOB') or\
               (answer == 'JOB KILL') or re.match(r'^ERROR', answer):
                break

        if (answer == 'GOOD JOB'):
            connect_job(job_id_lst[0], 1, openssh_cmd, cmd_ret) 
            # TODO exit(connect_job($Job_id_list_ref->[0],1,$Openssh_cmd));
            pass
        else:
            cmd_ret.exit(11)

    cmd_ret.exit(0)
