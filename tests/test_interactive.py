import unittest
import tempfile
from pathlib import Path
from kyper_workflow.interactive import run,resume
from kyper_workflow.runtime import execute_review
from kyper_workflow.usage import Ledger
from kyper_workflow.workflow import Workflow

RECORD={'sources':['https://example.org'],'source':'user','choice':'fixture','status':'pass'}
class InteractiveTests(unittest.TestCase):
 def test_operator_fixture_accept(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'a.py').write_text('x=1');answers=iter(['Check syntax','yes','https://docs.python.org','acknowledge','local','APPROVE 2'])
   result=run(state=p/'state',root=p,artifacts=['a.py'],read=lambda _:next(answers),write=lambda _:None,terminal=True)
   self.assertEqual(result['status'],'pass')
 def test_operator_fixture_reject(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);answers=iter(['Check syntax','yes','https://docs.python.org','acknowledge','local','NO'])
   result=run(state=p/'state',root=p,artifacts=['missing.py'],read=lambda _:next(answers),write=lambda _:None,terminal=True)
   self.assertEqual(result['status'],'cancelled')
 def test_no_pipe_approval(self):
  with self.assertRaises(ValueError):run(state='x',root='.',artifacts=['x'],terminal=False)

 def test_cancel_and_resume(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);(p/'a.py').write_text('x=1');answers=iter(['Check syntax','yes','https://docs.python.org','acknowledge','local','NO'])
   self.assertEqual(run(state=p/'state',root=p,artifacts=['a.py'],read=lambda _:next(answers),write=lambda _:None,terminal=True)['status'],'cancelled')
   self.assertEqual(resume(p/'state',read=lambda _:'APPROVE 2',write=lambda _:None,terminal=True)['status'],'pass')

 def plan(self,p,count):
  (p/'a.py').write_text('a=1\n');(p/'b.py').write_text('b=2\n')
  w=Workflow(p/'state',confirm=lambda shown:shown)
  for stage in ('research','direction_review','specification'):w.transition(stage,record=RECORD)
  w.revise('Two approved tasks')
  w.add_task('first',code_mode='syntax',acceptance='syntax',required_checks=['code'],
             inputs={'root':str(p.resolve()),'artifacts':['a.py']})
  w.add_task('second',depends=['first'],code_mode='syntax',acceptance='syntax',required_checks=['code'],
             inputs={'root':str(p.resolve()),'artifacts':['b.py']})
  for stage in ('specification_qa','awaiting_confirmation'):w.transition(stage,record=RECORD)
  w.approve();return w

 def test_resume_runs_remaining_approved_tasks(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);w=self.plan(p,2)
   first=execute_review(w,'first',root=p,artifacts=['a.py'],ledger=Ledger(str(p/'usage.json')))
   self.assertEqual(first['status'],'pass')
   result=resume(p/'state',read=lambda _:'APPROVE '+str(w.data['revision']),write=lambda _:None,terminal=True)
   self.assertEqual(result['status'],'pass')
   self.assertEqual(sorted(result['tasks']),['second'])
   self.assertEqual(Workflow(p/'state').data['state'],'complete')

 def test_resume_refuses_interrupted_running_task(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d);w=self.plan(p,2)
   w.start('first')
   with self.assertRaisesRegex(ValueError,'not replayed'):
    resume(p/'state',read=lambda _:'APPROVE '+str(w.data['revision']),write=lambda _:None,terminal=True)
