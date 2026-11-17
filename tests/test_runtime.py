import tempfile
import unittest
from pathlib import Path
from kyper_workflow.workflow import Workflow
from kyper_workflow.runtime import execute_review
from kyper_workflow.usage import Ledger
class RuntimeTests(unittest.TestCase):
 def test_confirm_then_execute_and_account(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'x.py').write_text('x=1');w=Workflow(root/'state',confirm=lambda x:x)
   for state in ('research','direction_review','specification'):w.transition(state,record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'})
   w.revise('syntax');w.add_task('x',code_mode='syntax',acceptance='syntax')
   for state in ('specification_qa','awaiting_confirmation'):w.transition(state,record={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'})
   l=Ledger()
   with self.assertRaises(ValueError):execute_review(w,'x',root=root,artifacts=['x.py'],ledger=l)
   self.assertEqual(l.attempts,[]);w.approve();r=execute_review(w,'x',root=root,artifacts=['x.py'],ledger=l)
   self.assertEqual(r['status'],'pass');self.assertIsNone(r['usage']['cost']);w.complete()
