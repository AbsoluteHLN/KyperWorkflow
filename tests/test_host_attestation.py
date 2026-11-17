"""Trusted host check attestation, restart recheck and ledger append behaviour."""
import json
import tempfile
import unittest
from pathlib import Path

from kyper_workflow.evidence import Review
from kyper_workflow.runtime import execute_review, recheck
from kyper_workflow.usage import Ledger
from kyper_workflow.workflow import Workflow


RECORD = {'sources': ['https://example.org'], 'source': 'user', 'choice': 'fixture', 'status': 'pass'}


def approved(root, required_checks, code_mode=None, inputs=None):
    workflow = Workflow(root / 'state.json', confirm=lambda shown: shown)
    for stage in ('research', 'direction_review', 'specification'):
        workflow.transition(stage, record=RECORD)
    workflow.revise('Reviewed specification')
    workflow.add_task('doc', writes=(), acceptance='Declared checks pass', code_mode=code_mode,
                      required_checks=required_checks, inputs=inputs)
    workflow.transition('specification_qa', record=RECORD)
    workflow.transition('awaiting_confirmation', record=RECORD)
    workflow.approve()
    return workflow


def attested(review, **detail):
    return review.attest('text', status='pass', detail=detail or {'notes': 'reviewed'},
                         revision=review.revision)


def reviewed(review):
    """Stand-in for host review: the verdict follows the content it was given."""
    detail = {'notes': 'reviewed current content'}
    status = 'fail' if b'Silently replaced' in review.original['draft.md'] else 'pass'
    return review.attest('text', status=status, detail=detail, revision=review.revision)


class HostAttestationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        (self.root / 'draft.md').write_text('# Draft\n\nText only.\n')
        self.inputs = {'root': str(self.root.resolve()), 'artifacts': ['draft.md']}

    def tearDown(self):
        self.directory.cleanup()

    def test_text_task_passes_through_attestation_then_completes(self):
        workflow = approved(self.root, ('text',), inputs=self.inputs)
        result = execute_review(workflow, 'doc', root=self.root, artifacts=['draft.md'],
                                ledger=Ledger(self.root / 'usage.json'), attest=attested)
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['review']['checks'], {'text': 'pass'})
        workflow.complete()
        self.assertEqual(workflow.data['state'], 'complete')

    def test_missing_attestation_is_blocked_not_passed(self):
        workflow = approved(self.root, ('text',), inputs=self.inputs)
        result = execute_review(workflow, 'doc', root=self.root, artifacts=['draft.md'],
                                ledger=Ledger(self.root / 'usage.json'))
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['review']['unattested_checks'], ['text'])
        self.assertFalse(result['review']['allow_completion'])

    def test_attestation_for_other_revision_is_rejected(self):
        workflow = approved(self.root, ('text',), inputs=self.inputs)
        review = Review(self.root, ['draft.md'], workflow.data['revision'])

        def stale(candidate):
            candidate.attest('text', status='pass', detail={'notes': 'x'},
                             revision=candidate.revision + 1)

        with self.assertRaises(ValueError):
            stale(review)

    def test_content_change_after_attestation_blocks_gate(self):
        workflow = approved(self.root, ('text',), inputs=self.inputs)
        result = execute_review(workflow, 'doc', root=self.root, artifacts=['draft.md'],
                                ledger=Ledger(self.root / 'usage.json'), attest=attested)
        self.assertEqual(result['status'], 'pass')
        (self.root / 'draft.md').write_text('# Draft\n\nRewritten.\n')
        with self.assertRaises(ValueError):
            workflow.complete()

    def test_code_check_cannot_be_attested_by_the_host(self):
        review = Review(self.root, ['draft.md'], 1)
        with self.assertRaises(ValueError):
            review.attest('code', status='pass', detail={'notes': 'x'}, revision=1)

    def test_non_source_artifact_is_blocked_not_failed(self):
        review = Review(self.root, ['draft.md'], 1)
        self.assertEqual(review.syntax()['status'], 'blocked')
        self.assertFalse(review.gate(['code'])['allow_completion'])

    def test_restart_recheck_restores_completion_for_passed_task(self):
        workflow = approved(self.root, ('text',), inputs=self.inputs)
        execute_review(workflow, 'doc', root=self.root, artifacts=['draft.md'],
                       ledger=Ledger(self.root / 'usage.json'), attest=attested)
        restored = Workflow(self.root / 'state.json')
        with self.assertRaises(ValueError):
            restored.complete()
        checked = recheck(restored, attest=attested)
        self.assertTrue(checked['doc']['allow_completion'])
        restored.complete()
        self.assertEqual(restored.data['state'], 'complete')

    def test_restart_recheck_does_not_trust_stored_result_after_edit(self):
        workflow = approved(self.root, ('text',), inputs=self.inputs)
        execute_review(workflow, 'doc', root=self.root, artifacts=['draft.md'],
                       ledger=Ledger(self.root / 'usage.json'), attest=reviewed)
        restored = Workflow(self.root / 'state.json')
        (self.root / 'draft.md').write_text('# Draft\n\nSilently replaced.\n')
        checked = recheck(restored, attest=reviewed)
        self.assertFalse(checked['doc']['allow_completion'])
        with self.assertRaises(ValueError):
            restored.complete()


class LedgerFormatTests(unittest.TestCase):
    def test_append_is_one_line_per_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.jsonl'
            ledger = Ledger(path)
            ledger.record(task='a', model='m', status='pass', source='unknown')
            ledger.record(task='b', model='m', status='pass', source='unknown')
            lines = [line for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
            self.assertEqual(len(lines), 2)
            self.assertEqual(Ledger(path).attempts, ledger.attempts)

    def test_legacy_array_file_is_migrated_on_append(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'usage.json'
            path.write_text(json.dumps([{'attempt_id': 'old', 'task': 'a', 'model': 'm',
                                         'status': 'fail', 'tokens': None, 'cost': None,
                                         'currency': None, 'source': 'unknown',
                                         'at': '2026-01-01T00:00:00+00:00'}]), encoding='utf-8')
            Ledger(path).record(task='b', model='m', status='pass', source='unknown')
            self.assertEqual([row['task'] for row in Ledger(path).attempts], ['a', 'b'])
            self.assertFalse(path.read_text(encoding='utf-8').lstrip().startswith('['))

    def test_unaccounted_reserve_can_cover_unknown_attempts(self):
        ledger = Ledger()
        ledger.record(task='a', model='m', status='pass', source='unknown')
        self.assertFalse(ledger.budget_allows(10, 'USD', next_max_cost=1))
        self.assertTrue(ledger.budget_allows(10, 'USD', next_max_cost=1, unaccounted_reserve=2))
        self.assertFalse(ledger.budget_allows(2, 'USD', next_max_cost=1, unaccounted_reserve=2))

    def test_measured_cost_plus_reserve_is_summed(self):
        ledger = Ledger()
        ledger.record(task='a', model='m', status='pass', cost=2, currency='USD', source='actual')
        ledger.record(task='b', model='m', status='pass', source='unknown')
        self.assertTrue(ledger.budget_allows(5, 'USD', next_max_cost=1, unaccounted_reserve=2))
        self.assertFalse(ledger.budget_allows(4, 'USD', next_max_cost=1, unaccounted_reserve=2))


if __name__ == '__main__':
    unittest.main()
