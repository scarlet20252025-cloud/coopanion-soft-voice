import unittest
from coopanion_soft_voice.memory_policy import loading_requirement

class MemoryPolicyTests(unittest.TestCase):
    def test_only_measured_compact_layout_has_lower_guard(self):
        config={'compactGraphs':True,'kvContext':1024,'speechOnly':{'format':1}}
        self.assertEqual(loading_requirement(config),3.25)
        for patch in ({'compactGraphs':False},{'kvContext':4096},{'speechOnly':{}}):
            self.assertEqual(loading_requirement({**config,**patch}),4)
        self.assertEqual(loading_requirement({}),4)
