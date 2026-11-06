import hashlib
import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from stockdb_sdk_bridge import IndustryQuery, QueryService
from stockdb_update_agent import UpdateAgent
from app.services.stockdb_files import FullResultCache, data_version, ensure_available, manifest_fingerprint, read_json, write_json


def row(date, price=10):
    return dict(date=date, open=price, high=price, low=price, close=price)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.control = self.root / 'control'
        write_json(self.control / 'version.json', {'status': 'ready', 'version': 'v1'})
        self.cache = FullResultCache(self.root / 'cache')

    def test_complete_result_survives_restart_and_slices_start(self):
        rows = [row(20240102), row(20240103)]
        with patch('stockdb_sdk_bridge.sdk_query', return_value=(rows, {})) as sdk:
            query = IndustryQuery('', self.control, self.cache)
            self.assertEqual(query('801080.SL', '1d', '20240103', '20240331')[0], rows[1:])
            restarted = IndustryQuery('', self.control, FullResultCache(self.root / 'cache'))
            result, timing = restarted('801080.SL', '1d', '20240101', '20240331')
            self.assertEqual(result, rows)
            self.assertEqual(timing['persistent_hit'], 1)
            sdk.assert_called_once_with('', '801080.SL', '1d', '20000101', '20240331')

    def test_same_date_new_version_and_partial_period_end_invalidate(self):
        with patch('stockdb_sdk_bridge.sdk_query', return_value=([row(20240102)], {})) as sdk:
            query = IndustryQuery('', self.control, self.cache)
            query('801080.SL', '1M', '20240101', '20240115')
            query('801080.SL', '1M', '20240101', '20240131')
            self.assertIsNone(self.cache.get('801080.SL@20240115', '1M', 'v1'))
            write_json(self.control / 'version.json', {'status': 'ready', 'version': 'v2'})
            query('801080.SL', '1M', '20240101', '20240131')
            self.assertEqual(sdk.call_count, 3)
            self.assertIsNone(self.cache.get('801080.SL@20240131', '1M', 'v1'))

    def test_failure_and_empty_result_do_not_persist(self):
        query = IndustryQuery('', self.control, self.cache)
        with patch('stockdb_sdk_bridge.sdk_query', side_effect=ValueError('SDK failed')):
            with self.assertRaises(ValueError):
                query('801080.SL', '1d', '20000101', 'N')
        with patch('stockdb_sdk_bridge.sdk_query', return_value=([], {})) as sdk:
            query('801080.SL', '1d', '20000101', 'N')
            query('801080.SL', '1d', '20000101', 'N')
            self.assertEqual(sdk.call_count, 2)

    def test_disk_hit_bypasses_other_sdk_work(self):
        self.cache.put('801080.SL@N', '1d', 'v1', [row(20240102)])
        entered, release = Event(), Event()
        def slow(*args):
            entered.set()
            self.assertTrue(release.wait(3))
            return [row(20240102)], {}
        service = QueryService(IndustryQuery('', self.control, self.cache))
        with patch('stockdb_sdk_bridge.sdk_query', side_effect=slow), ThreadPoolExecutor(2) as pool:
            task = pool.submit(service.get, ('600519', '1w', '20000101', 'N'), {})
            self.assertTrue(entered.wait(2))
            trace = {}
            try:
                result = pool.submit(service.get, ('801080.SL', '1d', '20000101', 'N'), trace).result(timeout=.5)
                self.assertEqual(json.loads(result), [row(20240102)])
                self.assertEqual(trace['source'], 'disk')
            finally:
                release.set()
            task.result(timeout=3)

    def test_maintenance_and_version_changes_block_memory_cache(self):
        def version(probe):
            if not probe:
                ensure_available(self.control)
            return data_version(self.control)
        query = Mock(return_value=([row(20240102)], {}))
        service = QueryService(lambda *args: query(*args), version_provider=version)
        key = ('600519', '1d', '20000101', 'N')
        service.get(key, {})
        write_json(self.control / 'maintenance.json', {})
        with self.assertRaises(RuntimeError):
            service.get(key, {})
        service.get(key, {}, probe=True)
        (self.control / 'maintenance.json').unlink()
        write_json(self.control / 'version.json', {'status': 'ready', 'version': 'v2'})
        service.get(key, {})
        self.assertEqual(query.call_count, 2)

    def snapshot(self):
        source = self.root / 'stockdb'
        data = source / 'data'
        data.mkdir(parents=True)
        (source / '数据更新.exe').write_bytes(b'fake')
        content = b'snapshot'
        (data / '1.ldb').write_bytes(content)
        write_json(data / '.sync_manifest.json', {'files': [{'path': '1.ldb', 'size': len(content), 'sha256': hashlib.sha256(content).hexdigest()}]})
        return source

    def test_version_changed_during_request_is_not_published(self):
        def query(*args):
            write_json(self.control / 'version.json', {'status': 'ready', 'version': 'v2'})
            return [row(20240102)], {}
        service = QueryService(query, version_provider=lambda probe: data_version(self.control))
        with self.assertRaisesRegex(RuntimeError, '版本'):
            service.get(('600519', '1d', '20000101', 'N'), {})
        self.assertEqual(service.metrics()['cache_entries'], 0)

    def test_memory_result_cache_obeys_byte_budget(self):
        query = Mock(return_value=([row(20240102)], {}))
        service = QueryService(lambda *args: query(*args))
        service.memory_limit = 10
        key = ('600519', '1d', '20000101', 'N')
        service.get(key, {})
        service.get(key, {})
        self.assertEqual(query.call_count, 2)
        self.assertEqual(service.metrics()['cache_entries'], 0)

    def test_failed_sha_verification_does_not_mark_new_version_ready(self):
        source = self.snapshot()
        (source / 'data/1.ldb').write_bytes(b'changed!')
        write_json(self.control / 'maintenance.json', {})
        runner = Mock(return_value=Mock(returncode=0, stdout=b'0', stderr=b''))
        agent = UpdateAgent(self.root, source, self.control, runner=runner)
        with patch('stockdb_update_agent.subprocess.Popen', return_value=Mock(pid=123, wait=Mock(return_value=0))):
            agent.execute({'task_id': 'job', 'operation': 'update'})
        self.assertEqual(read_json(self.control / 'status.json')['status'], 'failed')
        self.assertEqual(runner.call_count, 2)
        with self.assertRaises(RuntimeError):
            data_version(self.control)

    def test_manifest_catches_same_size_historical_correction_and_path_escape(self):
        source = self.snapshot()
        manifest_fingerprint(source, verify=True)
        (source / 'data/1.ldb').write_bytes(b'changed!')
        with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
            manifest_fingerprint(source, verify=True)
        write_json(source / 'data/.sync_manifest.json', {'files': [{'path': '../../outside', 'size': 1}]})
        with self.assertRaises(ValueError):
            manifest_fingerprint(source, verify=True)

    def test_agent_success_rotates_version_and_orders_stop_update_verify_start(self):
        source = self.snapshot()
        write_json(self.control / 'maintenance.json', {})
        runner = Mock(return_value=Mock(returncode=0, stdout=b'0', stderr=b''))
        agent = UpdateAgent(self.root, source, self.control, runner=runner)
        with patch('stockdb_update_agent.subprocess.Popen', return_value=Mock(pid=123, wait=Mock(return_value=0))):
            agent.execute({'task_id': 'job', 'operation': 'update'})
        status = read_json(self.control / 'status.json')
        self.assertEqual(status['status'], 'success')
        self.assertNotEqual(data_version(self.control), 'v1')
        commands = [call.args[0] for call in runner.call_args_list]
        self.assertIn('stop', commands[1])
        self.assertIn('up', commands[2])
        self.assertIn('/opt/healthcheck.py', commands[3])
        self.assertFalse((self.control / 'maintenance.json').exists())

    def test_agent_failed_updater_never_restarts_or_serves_old_cache(self):
        source = self.snapshot()
        write_json(self.control / 'maintenance.json', {})
        runner = Mock(return_value=Mock(returncode=0, stdout=b'0', stderr=b''))
        agent = UpdateAgent(self.root, source, self.control, runner=runner)
        with patch('stockdb_update_agent.subprocess.Popen', return_value=Mock(pid=123, wait=Mock(return_value=1))):
            agent.execute({'task_id': 'job', 'operation': 'update'})
        self.assertEqual(read_json(self.control / 'status.json')['status'], 'failed')
        self.assertEqual(runner.call_count, 2)
        with self.assertRaises(RuntimeError):
            data_version(self.control)
        self.assertTrue((self.control / 'maintenance.json').exists())


if __name__ == '__main__':
    unittest.main()
