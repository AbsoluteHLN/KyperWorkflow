"""Local attempt accounting and bounded progress supervision."""
import math
import copy
import json
import os
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone


def _parse_attempts(text):
    """Parse append-only JSONL, still accepting one legacy JSON array file."""
    if not text.strip():
        return []
    if text.lstrip().startswith('['):
        rows = json.loads(text)
        return rows if isinstance(rows, list) else None
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def _read_attempts(path):
    return _parse_attempts(path.read_text(encoding="utf-8"))


class Ledger:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else None
        self.attempts = _read_attempts(self.path) if self.path and self.path.exists() else []
        if not isinstance(self.attempts,list) or any(not isinstance(r,dict) or not r.get('attempt_id') or r.get('source') not in ('actual','estimated','unknown') for r in self.attempts):
            raise ValueError('Damaged usage ledger')
        self._loaded=copy.deepcopy(self.attempts)

    def record(self, *, task, model, status, tokens=None, cost=None, currency=None, source='unknown', attempt_id=None):
        if source not in ('actual', 'estimated', 'unknown') or status not in ('pass', 'fail', 'blocked'):
            raise ValueError('Invalid measurement')
        if source == 'unknown' and (tokens is not None or cost is not None):
            raise ValueError('Unknown usage cannot have numeric values')
        if any(v is not None and (type(v) not in (int,float) or not math.isfinite(v) or v < 0) for v in (tokens,cost)):
            raise ValueError('Invalid amount')
        if cost is not None and not currency: raise ValueError('Currency required')
        attempt_id=attempt_id or uuid4().hex
        if any(r['attempt_id']==attempt_id for r in self.attempts): raise ValueError('Duplicate attempt')
        row = dict(attempt_id=attempt_id,task=task, model=model, status=status, tokens=tokens, cost=cost,
                   currency=currency, source=source, at=datetime.now(timezone.utc).isoformat())
        if self.path:
            from .locking import writer_lock
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with writer_lock(self.path.with_name(self.path.name+'.lock')):
                existing=self.path.read_text(encoding='utf-8') if self.path.exists() else ''
                current=_parse_attempts(existing) if existing else []
                if not isinstance(current,list): raise ValueError('Damaged usage ledger')
                if current != self._loaded: raise ValueError('Usage ledger changed; reload')
                line=json.dumps(row,ensure_ascii=False)+'\n'
                if existing.lstrip().startswith('['):
                    # One-time rewrite; appending would corrupt the old array file.
                    temp=self.path.with_name(self.path.name+'.'+uuid4().hex+'.tmp')
                    temp.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in self.attempts+[row]), encoding='utf-8')
                    os.replace(temp,self.path)
                else:
                    with self.path.open('a',encoding='utf-8') as handle:handle.write(line)
        self.attempts.append(row)
        self._loaded=copy.deepcopy(self.attempts)
        return dict(row)

    def budget_allows(self, ceiling, currency, *, next_max_cost=None, unaccounted_reserve=None):
        """Fail closed unless every non-measured attempt is covered by a reserve.

        unaccounted_reserve is caller-declared money for attempts whose cost is
        unknown; without it an unknown or estimated row blocks the hard budget.
        """
        if type(ceiling) not in (int,float) or not math.isfinite(ceiling) or ceiling < 0: return False
        if type(next_max_cost) not in (int,float) or not math.isfinite(next_max_cost) or next_max_cost < 0: return False
        if unaccounted_reserve is not None and (type(unaccounted_reserve) not in (int,float) or not math.isfinite(unaccounted_reserve) or unaccounted_reserve < 0): return False
        if not self.attempts: return False
        accounted = 0.0
        for row in self.attempts:
            if row['source'] == 'actual' and row['cost'] is not None and row['currency'] == currency:
                accounted += row['cost']
            elif unaccounted_reserve is not None and row['currency'] in (None, currency):
                continue
            else:
                return False
        return accounted + (unaccounted_reserve or 0) + next_max_cost <= ceiling


class Supervisor:
    def __init__(self): self.blockers = {}; self.progress = []; self.noise = {}
    def observe(self, task, *, kind, detail):
        if kind not in ('artifact', 'acceptance', 'research_source', 'active_build', 'blocker', 'noise'):
            raise ValueError('Unknown observation')
        if not detail: raise ValueError('Observation evidence required')
        if kind == 'blocker':
            previous, count = self.blockers.get(task, (None, 0))
            count = count + 1 if detail == previous else 1
            self.blockers[task] = (detail, count)
            return {'action': 'pause' if count >= 2 else 'inspect', 'same_blocker_count': count}
        if kind == 'noise':
            self.noise[task] = self.noise.get(task,0)+1
            if self.noise[task] >= 2:return {'action':'pause','reason':'No useful progress'}
        if kind != 'noise':
            self.noise[task] = 0
            self.progress.append((task, kind, detail))
            self.blockers.pop(task, None)
        return {'action': 'wait' if kind == 'active_build' else 'continue' if kind != 'noise' else 'inspect'}

    def model_check(self, task, *, reviewer=None, authorize=None, ledger=None, model='unknown'):
        """Optional cheap host review at scheduler checkpoints; never self-schedules."""
        if reviewer is None or authorize is None or authorize(task,model) is not True:
            return {'status':'blocked','reason':'Authorized supervisory host unavailable'}
        if getattr(self,'_reviewing',False):return {'status':'blocked','reason':'Recursive supervision rejected'}
        self._reviewing=True
        try:
            response=reviewer({'task':task,'progress':list(self.progress),'blocker':self.blockers.get(task)})
            if not isinstance(response,dict) or response.get('action') not in ('continue','inspect','pause'):
                raise ValueError('Invalid supervisory response')
            if ledger is not None:
                usage=response.get('usage') or {}
                ledger.record(task=task,model=model,status='pass',tokens=usage.get('tokens'),cost=usage.get('cost'),currency=usage.get('currency'),source=usage.get('source','unknown'))
            # A model opinion cannot turn a repeated blocker into completion.
            if self.blockers.get(task,(None,0))[1]>=2 or self.noise.get(task,0)>=2:
                response=dict(response,action='pause')
            return {'status':'reviewed','action':response['action'],'opinion':response.get('reason'), 'allow_completion':False}
        except Exception as exc:
            if ledger is not None:ledger.record(task=task,model=model,status='fail')
            return {'status':'blocked','reason':type(exc).__name__}
        finally:self._reviewing=False
