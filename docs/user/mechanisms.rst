Mechanisms
==========

.. _INTERACTIVE:

How does an interactive *oarsub* work?
--------------------------------------

.. figure:: ../_static/interactive_oarsub_scheme.png
   :align: center
   :alt: interactive oarsub decomposition
   :target: ../_static/interactive_oarsub_scheme.svg

   Interactive oarsub decomposition


Job launch
----------

For PASSIVE jobs, the mechanism is similar to the :ref:`interactive
<INTERACTIVE>` one, except for the shell launched from the frontal node.

The job is finished when the user command ends. Then oarexec return its exit
value (what errors occured) on the Almighty via the SERVER_PORT if
DETACH_JOB_FROM_SERVER was set to 1 otherwise it returns directly.


CPUSET
------

The cpuset name is effectively created on each nodes and is composed as
``user_jobid``.

OAR system steps:

 1. Before each job, the Runner initialize the CPUSET (see `CPUSET
    definition`) with OPENSSH_CMD and an efficient launching tool :
    `Taktuk <http://taktuk.gforge.inria.fr/>`_.
    The processors assigned to this cpuset are taken from the defined database
    field by JOB_RESOURCE_MANAGER_PROPERTY_DB_FIELD in the table resources.

 2. After each job, OAR deletes all processes stored in the associated CPUSET.
    Thus all nodes are clean after a OAR job.

If you don't want to use this feature, you can, but nothing will warranty that
every user processes will be killed after the end of a job.

If you want you can implement your own cpuset management. This is done by
editing 3 files (see also `CPUSET installation`):

 - cpuset_manager.pl : this script creates the cpuset on each nodes
   and also delete it at the end of the job. For more informations, you have to
   look at this script (there are several comments).

 - oarsh : (OARSH) this script is used to replace the standard ``ssh``
   command. It gets the cpuset name where it is running and transfer this
   information via ``ssh`` and the ``SendEnv`` option. In this file, you have
   to change the ``get_current_cpuset`` function.

 - oarsh_shell : (OARSH_SHELL) this script is the shell of the oar user on
   each nodes. It gets environment variables and look at if there is a cpuset
   name. So if there is one it assigns the current process and its father to
   this cpusetname. So all further user processes will remind in the cpuset.
   In this file you just have to change the ``add_process_to_cpuset`` function.

SSH connection key definition
-----------------------------

This function is performed by :doc:`commands/oarsub` with the --ssh_private_key
and --ssh_public_key options.

It enables the user to define a ssh key pair to connect on their nodes. So
oarsh can be used on nodes of different clusters to connect each others if the
same ssh keys are used with each :doc:`commands/oarsub`.

So a grid reservation (``-r`` option of :doc:`commands/oarsub` on each OAR batch
scheduler of each wanted clusters) can be done with this functionality.

Example::

    ssh-keygen -f oar_key
    oarsub --ssh_private_key ``$(cat oar_key)`` --ssh_public_key ``$(cat oar_key.pub)`` ./script.sh


Suspend/resume
--------------

Jobs can be suspended with the command :doc:`commands/oarhold` (send a
``SIGSTOP`` on every processes on every nodes) to allow other jobs to be
executed.

``Suspended`` jobs can be resumed with the command :doc:`commands/oarresume`
(send a ``SIGSTOP`` on every suspended processes on every nodes). They will
pass into ``Running`` when assigned resources will be free.

IMPORTANT: This feature is available only if CPUSET_ is
configured.

You can specify 2 scripts if you have to perform any actions just after
(JUST_AFTER_SUSPEND_EXEC_FILE) suspend and just before resume
(JUST_BEFORE_RESUME_EXEC_FILE).

Moreover you can perform other actions (than send signals to processes)
if you want: just edit the ``suspend_resume_manager.pl`` file.

Job deletion
------------

Leon tries to connect to OAR Perl script running on the first job node (find
it thanks to the file :file:`/tmp/oar/pid_of_oarexec_for_jobId_id`) and sends a
``SIGTERM`` signal. Then the script catch it and normally end the job (kill
processes that it has launched).

If this method didn't succeed then Leon will flush the OAR database for the
job and nodes will be ``Suspected`` by NodeChangeState.

If your job is check pointed and is of the type *idempotent*
(:doc:`commands/oarsub` ``-t`` option) and its exit code is equal to 99 then
another job is automatically created and scheduled with same behaviours.

Checkpoint
----------

The checkpoint is just a signal sent to the program specified with the
:doc:`commands/oarsub` command.

If the user uses ``--checkpoint`` option then Sarko will ask the OAR Perl script
running on the first node to send the signal to the process (``SIGUSR2`` or the one
specified with ``--signal``).

You can also use :doc:`commands/oardel` command to send the signal.

Scheduling
----------

General steps used to schedule a job:

  1. All previous scheduled jobs are stored in a Gantt data structure.

  2. All resources that match property constraints of the job(``-p`` option and
     indication in the ``{...}`` from the ``-l`` option of the
     :doc:`commands/oarsub`) are stored in a tree data structure according to
     the hierarchy given with the ``-l`` option.

  3. Then this tree is given to the Gantt library to find the first hole where
     the job can be launched.

  4. The scheduler stores its decision into the database in the
     gantt_jobs_predictions and gantt_jobs_resources tables.

See User section from the FAQ for more examples and features.

Job dependencies
----------------

A job dependency is a situation where a job needs the ending of another job
to start. OAR deals with job dependency problems by refusing to schedule
dependant jobs if their required job is in Terminated state and have an exit
code != 0 (an error occured). If the required job is resubmited, its jobId is
no longer the same and OAR updates the database and sets the job_id_required
field to this new jobId for the dependant job.

:Note: The queues configured with the quota features
       (*oar_sched_gantt_with_timesharing_and_fairsharing_and_quotas*) have a
       different behaviour.
       This scheduler always launches dependant jobs even if there required
       jobs are in *Error* state or with an exit code != 0.

User notification
-----------------

This section explains how the ``--notify`` :doc:`commands/oarsub` option is
handled by OAR:

 - The user wants to receive an email: The syntax is ``mail:name@domain.com``.
   Mail section in the `Configuration file` must be present otherwise the mail
   cannot be sent. The subject of the mail is of the form:

     \*OAR\* [*TAG*]: job_id (job_name) on OAR_server_hostname


 - The user wants to launch a script: The syntax is ``exec:/path/to/script
   args``. OAR server will connect (using OPENSSH_CMD) on the node where the
   :doc:`commands/oarsub` command was invoked and then launches the script with
   the following arguments : *job_id*, *job_name*, *TAG*, *comments*.

*TAG* can be:
  - RUNNING : when the job is launched
  - END : when the job is finished normally
  - ERROR : when the job is finished abnormally
  - INFO : used when oardel is called on the job
  - SUSPENDED : when the job is suspended
  - RESUMING : when the job is resumed

Accounting aggregator
---------------------

In the `Configuration file` you can set the ACCOUNTING_WINDOW parameter. Thus
the command oaraccounting will split the time with this amount and feed the
table accounting.

So this is very easily and faster to get usage statistics of the cluster. We
can see that like a ``data warehousing`` information extraction method.

Dynamic nodes coupling features
-------------------------------

We are working with the `Icatis <http://www.icatis.com/>`_ company on clusters
composed by Intranet computers. These nodes can be switch in computing mode
only at specific times. So we have implemented a functionality that can
request to power on some hardware if they can be in the cluster.

We are using the field *available_upto* from the table resources
to know when a node will be inaccessible in the cluster mode (easily settable
with oarnodesetting command). So when the OAR scheduler wants some potential
available computers to launch the jobs then it executes the command
SCHEDULER_NODE_MANAGER_WAKE_UP_CMD.

Moreover if a node didn't execute a job for SCHEDULER_NODE_MANAGER_IDLE_TIME
seconds and no job is scheduled on it before SCHEDULER_NODE_MANAGER_SLEEP_TIME
seconds then OAR will launch the command SCHEDULER_NODE_MANAGER_SLEEP_CMD.

.. _timesharing-anchor:

Timesharing
-----------

It is possible to share the slot time of a job with other ones. To perform this
feature you have to specify the type *timesharing* when you use
:doc:`commands/oarsub`.



Container jobs
--------------

With this functionality it is possible to execute jobs within another one. So
it is like a sub-scheduling mechanism.

First a job of the type *container* must be submitted, for example::

    oarsub -I -t container -l nodes=10,walltime=2:10:00
    ...
    OAR_JOB_ID=42
    ...

Then it is possible to use the *inner* type to schedule the new jobs within the
previously created container job::

    oarsub -I -t inner=42 -l nodes=7
    oarsub -I -t inner=42 -l nodes=1
    oarsub -I -t inner=42 -l nodes=10

Notes:

    - In the case:
      ::

        oarsub -I -t inner=42 -l nodes=11

      This job will never be scheduled because the container job ``42`` reserved only 10
      nodes.
    - ``-t container`` is handled by every kind of jobs (passive, interactive and
      reservations). But ``-t inner=...`` cannot be used with a reservation.

Besteffort jobs
---------------

Besteffort jobs are scheduled in the besteffort queue. Their particularity is
that they are deleted if another not besteffort job wants resources where they
are running.

For example you can use this feature to maximize the use of your cluster with
multiparametric jobs. This what it is done by the
`CIGRI <http://cigri.ujf-grenoble.fr>`_ project.

When you submit a job you have to use ``-t besteffort`` option of
:doc:`commands/oarsub` to specify that this is a besteffort job.

Important : a besteffort job cannot be a reservation.

If your job is of the type *besteffort* and *idempotent*
(:doc:`commands/oarsub` ``-t`` option) and killed by the OAR scheduler then
another job is automatically created and scheduled with same behaviours.

Cosystem jobs
-------------

This feature enables to reserve some resources without launching any
program on corresponding nodes. Thus nothing is done by OAR on computing nodes
when a job is starting except on the COSYSTEM_HOSTNAME defined in the
configuration file.

This is useful with an other launching system that will declare its time
slot in OAR. So yo can have two different batch scheduler.

When you submit a job you have to use ``-t cosystem`` option of
:doc:`commands/oarsub` to specify that this is a cosystem job.

These jobs are stopped by the :doc:`commands/oardel` command or when they reach
their walltime or their command has finished. They also use the node
COSYSTEM_HOSTNAME to launch the specified program or shell.

Deploy jobs
-----------

This feature is useful when you want to enable the users to reinstall their
reserved nodes. So the OAR jobs will not log on the first computer of the
reservation but on the DEPLOY_HOSTNAME.

So prologue and epilogue scripts are executed on DEPLOY_HOSTNAME and if the
user wants to launch a script it is also executed on DEPLOY_HOSTNAME.

OAR does nothing on computing nodes because they normally will be rebooted to
install a new system image.

This feature is strongly used in the `Grid5000 <https://www.grid5000.fr/>`_
project with `Kadeploy <http://ka-tools.imag.fr/>`_ tools.

When you submit a job you have to use ``-t deploy`` option of
:doc:`commands/oarsub` to specify that this is a deploy job.

Quotas
------
The administrator can limit the number of resources used by user, job types,
project ans queue (or a combination of them).
This feature acts like quotas. When one of the defined rules is reached then
next jobs will not be scheduled at this time. The scheduler will find another
slot when the quotas will be satisfied.

This feature is available in queues which use the scheduler
``oar_sched_gantt_with_timesharing_and_fairsharing_and_quotas``.

The quota rules are defined in :file:`/etc/oar/scheduler_quotas.conf`.

By default no quota is applied.

*Note1*: Quotas are applied globally, only the jobs of the type ``container`` are
not taken in account (but the inner jobs are used to compute the quotas).

*Note2*: Besteffort jobs are not taken in account except in the besteffort
queue.

Desktop computing
-----------------

If you cannot contact the computers via SSH you can install the ``desktop
computing`` OAR mode.
This kind of installation is based on two programs:

 - oar-cgi : this is a web CGI used by the nodes to communicate with
   the OAR server via a HTTP server on the OAR server node.

 - oar-agent.pl : This program asks periodically the server web CGI to know what it
   has to do.

This method replaces the SSH command. Computers which want to register them
into OAR just has to be able to contact OAR HTTP server.

In this situation we don't have a NFS file system to share the same directories
over all nodes so we have to use a stagein/stageout solution. In this case you
can use the :doc:`commands/oarsub` option ``stagein`` to migrate your data.
