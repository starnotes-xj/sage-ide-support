import json
import subprocess
import unittest
from unittest.mock import patch

from probe_runtime_contracts import MARKER, probe


class RuntimeProbeTest(unittest.TestCase):
    def run_probe(self, effects):
        with patch('probe_runtime_contracts.subprocess.run', side_effect=effects):
            return probe('f()', distro='Ubuntu', sage='/env/bin/sage', runs=2)

    def result(self, name, noise=''):
        return subprocess.CompletedProcess([], 0, noise + MARKER + json.dumps(name) + '\n', '')

    def test_consistent_result_is_observation_not_global_contract(self):
        result = self.run_probe([self.result('sage.rings.integer.Integer')] * 2)
        self.assertEqual(result['state'], 'OBSERVED_STABLE')
        self.assertEqual(result['observedReturnType'], 'sage.rings.integer.Integer')
        self.assertIsNone(result['returnType'])
        self.assertTrue(result['requiresSourceProof'])

    def test_external_python_types_remain_visible(self):
        result = self.run_probe([self.result('random.Random')] * 2)
        self.assertEqual(result['observedReturnType'], 'random.Random')

    def test_builtin_none_is_normalized(self):
        result = self.run_probe([self.result('builtins.NoneType')] * 2)
        self.assertEqual(result['observedReturnType'], 'None')

    def test_conflicting_results_are_retained(self):
        result = self.run_probe([self.result('builtins.str'), self.result('builtins.int')])
        self.assertEqual(result['state'], 'UNKNOWN')
        self.assertEqual(result['observations'], ['builtins.str', 'builtins.int'])

    def test_timeout_does_not_abort_batch(self):
        result = self.run_probe([subprocess.TimeoutExpired('wsl', 40), self.result('builtins.int')])
        self.assertEqual(result['state'], 'UNKNOWN')
        self.assertIn('TimeoutExpired', result['errors'][0])

    def test_unframed_output_is_not_type_evidence(self):
        result = self.run_probe([subprocess.CompletedProcess([], 0, 'sage.Fake\n', '')] * 2)
        self.assertEqual(result['observations'], [])
        self.assertEqual(len(result['errors']), 2)

    def test_other_stdout_does_not_obscure_type(self):
        result = self.run_probe([self.result('builtins.str', 'Starting...\n')] * 2)
        self.assertEqual(result['observedReturnType'], 'str')


if __name__ == '__main__':
    unittest.main()
