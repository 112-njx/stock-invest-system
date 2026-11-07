import hashlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'deploy/stockdb'))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'stock_backend/app/services'))
from update_control import Controller
from stockdb_files import read_json, write_json


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)/'control'
        self.data = Path(self.temp.name)/'source'
        self.data.mkdir()
        self.calls = []
        self.controller = Controller(self.root,self.data,lambda:self.calls.append('start'),lambda:self.calls.append('stop'),lambda:self.calls.append('probe'))
        self.controller.task = str(uuid4())

    def tearDown(self):
        self.temp.cleanup()

    def install(self, output):
        program = self.data/'数据更新'
        program.write_text('#!/usr/bin/env python3\n'+output,encoding='utf-8')
        program.chmod(0o755)
        (self.data/'sync_url.txt').write_text('isolated-test')

    def test_event_parser_deduplicates_retry_counts_and_preserves_all_events(self):
        c = self.controller
        c.report('downloading',15,'begin')
        for line in ('待下载资源数: 26个','待删除资源数: 24个','进度 [13/26] 正在下载 007593.ldb','续传 2 007593.ldb','续传 1 007593.ldb','续传 range007593.ldb part 2','range merged ok 007593.ldb','177.0M/528.1M (33.5%) 27.42M/s'):
            c.line(line)
        state = read_json(self.root/'status.json')
        self.assertEqual(state['details']['download_files'],26)
        self.assertEqual(state['details']['download_percent'],33.5)
        self.assertLess(state['progress'],75)
        with c.events.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],9)
            self.assertEqual(db.execute('SELECT file,status,retries FROM files').fetchall(),[('007593.ldb','done',2)])

    @unittest.skipIf(sys.platform == 'win32','Linux PTY integration')
    def test_complete_pipeline_uses_only_temporary_test_directory(self):
        data = self.data/'data';data.mkdir()
        content=b'isolated fixture';(data/'1.ldb').write_bytes(content)
        write_json(data/'.sync_manifest.json',{'files':[{'path':'1.ldb','size':len(content),'sha256':hashlib.sha256(content).hexdigest()}]})
        self.install("print('待下载资源数: 1个',flush=True)\nprint('进度 [1/1] ok 1.ldb',flush=True)\nprint('Success: 同步已 100% 完成!',flush=True)\n")
        self.controller.execute({'task_id':self.controller.task,'operation':'update'})
        self.assertEqual(read_json(self.root/'status.json')['status'],'success')
        self.assertEqual(self.calls,['stop','start','probe'])
        self.assertFalse((self.root/'maintenance.json').exists())
        self.assertEqual((data/'1.ldb').read_bytes(),content)

    @unittest.skipIf(sys.platform == 'win32','Linux PTY integration')
    def test_zero_exit_without_success_marker_is_failure(self):
        self.install("print('error: cannot open config',flush=True)\n")
        self.controller.execute({'task_id':self.controller.task,'operation':'update'})
        self.assertEqual(read_json(self.root/'status.json')['status'],'failed')
        self.assertTrue((self.root/'maintenance.json').exists())
        self.assertNotIn('start',self.calls)

    def test_restart_does_not_resume_partially_written_data(self):
        (self.root/'maintenance.json').touch()
        write_json(self.root/'status.json',{'task_id':self.controller.task,'status':'running'})
        self.controller.recover()
        self.assertEqual(read_json(self.root/'status.json')['status'],'failed')
        self.assertTrue((self.root/'maintenance.json').exists())
        self.assertEqual(self.calls,[])

    def test_probe_failure_keeps_maintenance_and_invalidates_version(self):
        (self.data/'数据更新').touch();(self.data/'数据更新').chmod(0o755)
        (self.data/'sync_url.txt').touch()
        self.controller.run_updater = Mock(side_effect=RuntimeError('download interrupted'))
        self.controller.execute({'task_id':self.controller.task,'operation':'update'})
        self.assertEqual(read_json(self.root/'version.json')['status'],'failed')
        self.assertEqual(read_json(self.root/'status.json')['details']['failed_phase'],'downloading')

    def test_queued_without_request_becomes_retryable_failure(self):
        (self.root/'maintenance.json').touch()
        write_json(self.root/'status.json',{'task_id':self.controller.task,'status':'queued'})
        self.controller.recover()
        self.assertEqual(read_json(self.root/'status.json')['status'],'failed')

    def test_runtime_orphan_recovery_has_a_grace_period_and_runs_once(self):
        marker = self.root/'maintenance.json'
        marker.touch()
        write_json(self.root/'status.json',{'task_id':self.controller.task,'status':'queued'})
        timestamp = marker.stat().st_mtime
        self.assertFalse(self.controller.recover_orphan(now=timestamp+29))
        self.assertEqual(read_json(self.root/'status.json')['status'],'queued')
        self.assertTrue(self.controller.recover_orphan(now=timestamp+31))
        self.assertEqual(read_json(self.root/'status.json')['status'],'failed')
        self.assertEqual(self.calls,['stop'])
        self.assertTrue(marker.exists())
        self.assertFalse(self.controller.recover_orphan(now=timestamp+60))

    def test_runtime_recovery_does_not_consume_a_published_job(self):
        marker = self.root/'maintenance.json'; marker.touch()
        job = {'task_id':self.controller.task,'operation':'update'}
        write_json(self.root/'request.json',job)
        self.assertFalse(self.controller.recover_orphan(now=marker.stat().st_mtime+60))
        self.assertEqual(read_json(self.root/'request.json'),job)
        self.assertEqual(self.calls,[])

    def test_runtime_recovery_handles_idle_state_and_abandoned_claim(self):
        marker = self.root/'maintenance.json'; marker.touch()
        write_json(self.root/'status.json',{'task_id':self.controller.task,'status':'idle'})
        write_json(self.root/'active-request.json',{'task_id':self.controller.task})
        self.assertTrue(self.controller.recover_orphan(now=marker.stat().st_mtime+60))
        self.assertFalse((self.root/'active-request.json').exists())

    @unittest.skipIf(sys.platform == 'win32','Linux PTY integration')
    def test_failed_hash_does_not_restart_data_readers(self):
        data = self.data/'data';data.mkdir()
        (data/'1.ldb').write_bytes(b'bad')
        write_json(data/'.sync_manifest.json',{'files':[{'path':'1.ldb','size':3,'sha256':'0'*64}]})
        self.install("print('Success: 同步已 100% 完成!',flush=True)\n")
        self.controller.execute({'task_id':self.controller.task,'operation':'update'})
        self.assertEqual(read_json(self.root/'status.json')['status'],'failed')
        self.assertNotIn('start',self.calls)


if __name__ == '__main__':
    unittest.main()
