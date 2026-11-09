import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name, ROOT/'blender_codex'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
layout=load('panel_layout');auto=load('auto_connect')

class FloatingTests(unittest.TestCase):
    def test_free_position_and_both_dimensions_survive_reopen_and_dpi_change(self):
        value=layout.normalize((70,80,350,430),(0,0,1000,800))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'layout.json';layout.save(path,value)
            self.assertEqual(layout.restore(layout.load(path),(0,0,2000,1600)),(140,160,700,860))
    def test_small_windows_keep_whole_panel_reachable(self):
        self.assertEqual(layout.clamp_bounds((-99,900,900,900),(10,20,150,90)),(10,20,150,90))
    def test_invalid_layout_is_rejected(self):
        for value in ({'version':2,'bounds':[0,0,1,1]}, {'version':1,'bounds':[float('nan'),0,1,1]}):
            with self.assertRaises(ValueError):layout.restore(value,(0,0,1000,800))
    def test_bounded_retries_no_turn_replay(self):
        policy=auto.AutoConnect();connect=Mock();session=NS(ready=False,busy=False,client=None,error='offline')
        for now in range(0,200,40):policy.tick(session,connect,now)
        for now in range(200,1000,40):policy.tick(session,connect,now)
        self.assertEqual(connect.call_count,5)
    def test_busy_and_existing_connection_are_reused(self):
        policy=auto.AutoConnect();connect=Mock();session=NS(ready=False,busy=True,client=None,error='')
        policy.tick(session,connect,0);session.busy=False;session.client=object();policy.tick(session,connect,10)
        connect.assert_not_called()
    def test_auth_failure_blocks_loop_and_explicit_request_allows_one_retry(self):
        policy=auto.AutoConnect();connect=Mock();session=NS(ready=False,busy=False,client=None,error='')
        policy.tick(session,connect,0);session.error='Run codex login';policy.tick(session,connect,100)
        self.assertEqual(connect.call_count,1)
        policy.request();policy.tick(session,connect,101);self.assertEqual(connect.call_count,2)
    def test_real_disconnect_after_success_reconnects_without_sending(self):
        policy=auto.AutoConnect();connect=Mock();session=NS(ready=True,busy=False,client=object(),error='')
        policy.tick(session,connect,0);session.ready=False;session.client=None;policy.tick(session,connect,2)
        connect.assert_called_once()

if __name__=='__main__':unittest.main()
