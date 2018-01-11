# coding: utf-8
import pytest

from oar.modules.bipbip import BipBip

from oar.lib import (db, config, Job, Challenge, Resource, AssignedResource, EventLog)

from oar.lib.job_handling import insert_job

import oar.lib.tools  # for monkeypatching

fake_bad_nodes = {'pingchecker': [], 'init': [], 'clean': []}
fake_tag = 1

def set_fake_tag(tag_value):
    global fake_tag
    fake_tag = tag_value

def fake_pingchecker(hosts):
     return fake_bad_nodes['pingchecker']

def fake_launch_oarexec(cmt,data, oarexec_files):
    return True

def fake_manage_remote_commands(hosts, data_str, manage_file, action, ssh_command, taktuk_cmd=None):
    return (fake_tag, fake_bad_nodes[action])

@pytest.fixture(scope='function', autouse=True)
def monkeypatch_tools(request, monkeypatch):
    monkeypatch.setattr(oar.lib.tools, 'create_almighty_socket', lambda: None)
    monkeypatch.setattr(oar.lib.tools, 'notify_almighty', lambda x: True)
    monkeypatch.setattr(oar.lib.tools, 'pingchecker', fake_pingchecker)
    monkeypatch.setattr(oar.lib.tools, 'notify_interactif_user', lambda x,y: None)
    monkeypatch.setattr(oar.lib.tools, 'launch_oarexec', fake_launch_oarexec)
    monkeypatch.setattr(oar.lib.tools, 'manage_remote_commands', fake_manage_remote_commands)

        
def test_bipbip_void():
    bipbip = BipBip(None)
    bipbip.run()
    print(bipbip.exit_code)
    assert bipbip.exit_code == 1

def test_bipbip_simple():
    job_id = insert_job(res=[(60, [('resource_id=4', '')])], properties='')
    Challenge.create(job_id=job_id, challenge='foo1', ssh_private_key='foo2', ssh_public_key='foo2')
    
    # Bipbip needs a job id
    bipbip = BipBip([job_id])
    bipbip.run()
    print(bipbip.exit_code)
    assert bipbip.exit_code == 1

def _test_bipbip_toLaunch(noop=False, job_id=None):

    types = ['noop'] if noop else []
    if not job_id:
        job_id = insert_job(res=[(60, [('resource_id=4', '')])], properties='', command='yop',
                            state='toLaunch', stdout_file='poy', stderr_file='yop', types=types)
    db.query(Job).update({Job.assigned_moldable_job: job_id}, synchronize_session=False)
    Challenge.create(job_id=job_id, challenge='foo1', ssh_private_key='foo2', ssh_public_key='foo2')

    resources = db.query(Resource).all()
    for r in resources[:4]:
        AssignedResource.create(moldable_id=job_id, resource_id=r.id)

    config['SERVER_HOSTNAME'] = 'localhost'
    config['DETACH_JOB_FROM_SERVER'] = 'localhost'
    
    # Bipbip needs a job id
    bipbip = BipBip([job_id])
    bipbip.run()

    return job_id, bipbip

def test_bipbip_toLaunch():
    _, bipbip = _test_bipbip_toLaunch()
    print(bipbip.exit_code)
    assert bipbip.exit_code == 0

def test_bipbip_toLaunch_noop():
    _, bipbip = _test_bipbip_toLaunch(noop=True)
    print(bipbip.exit_code)
    assert bipbip.exit_code == 0


def test_bipbip_toLaunch_cpuset_error():
    fake_bad_nodes['init'] = ['localhost0']
    job_id, bipbip = _test_bipbip_toLaunch()
    fake_bad_nodes['init'] = []
    event = db.query(EventLog).filter(EventLog.job_id==job_id).first()
    
    print(bipbip.exit_code)
    assert event.type == 'CPUSET_ERROR'
    assert bipbip.exit_code == 2

def test_bipbip_toLaunch_cpuset_error_advance_reservation():
    job_id = insert_job(res=[(60, [('resource_id=4', '')])], properties='', command='yop',
                        state='toLaunch', stdout_file='poy', stderr_file='yop',
                        reservation='Scheduled')
    fake_bad_nodes['init'] = ['localhost0']
    _, bipbip = _test_bipbip_toLaunch(job_id=job_id)
    fake_bad_nodes['init'] = []
    event = db.query(EventLog).filter(EventLog.job_id==job_id).first()
    
    print(bipbip.exit_code)
    assert event.type == 'CPUSET_ERROR'
    assert bipbip.exit_code == 0
