import unittest
from coopanion_soft_voice.memory_policy import loading_requirement

class MemoryPolicyTests(unittest.TestCase):
    def test_only_measured_compact_layout_has_lower_guard(self):
        config={'compactGraphs':True,'kvContext':1024,'speechOnly':{'format':1}}
        self.assertEqual(loading_requirement(config),3.25)
        self.assertEqual(loading_requirement({**config,'streamTextEmbedding':True}),3)
        self.assertEqual(loading_requirement({'streamTextEmbedding':True}),4)
        self.assertEqual(loading_requirement({**config,'streamTextEmbedding':'true'}),3.25)
        for patch in ({'compactGraphs':False},{'kvContext':4096},{'speechOnly':{}}):
            self.assertEqual(loading_requirement({**config,**patch}),4)
        self.assertEqual(loading_requirement({}),4)

    def test_lower_discrete_guard_requires_verified_layout_and_nvidia_identity(self):
        c={'compactGraphs':True,'kvContext':1024,'speechOnly':{'format':1},
           'streamTextEmbedding':True,'adaptiveKv':True,'deviceType':'discrete','vendorId':0x10de}
        self.assertEqual(loading_requirement(c),2.75)
        for patch in ({'adaptiveKv':False},{'deviceType':'integrated'},{'vendorId':0x1002},{'vendorId':None}):
            self.assertEqual(loading_requirement({**c,**patch}),3)
        self.assertEqual(loading_requirement({**c,'speechOnly':{}}),4)
