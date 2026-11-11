import tempfile
import unittest
from pathlib import Path
from demo import create_demo
from store import Store

class ReleaseTests(unittest.TestCase):
    def test_demo_is_synthetic_and_refuses_existing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=create_demo(Path(tmp)/'demo')
            s=Store(root)
            self.assertEqual(len(s.rows('SELECT * FROM versions')),3)
            before=s.db.read_bytes()
            with self.assertRaises(ValueError): create_demo(root)
            self.assertEqual(before,s.db.read_bytes())
            self.assertIn('虚构演示',s.rows('SELECT script FROM episodes WHERE id=1')[0]['script'])
