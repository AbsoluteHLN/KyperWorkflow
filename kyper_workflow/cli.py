"""Local explicit actions. No automatic user confirmation through model inputs."""
import argparse
import json
import sys
from pathlib import Path
from .evidence import Review
from .workflow import Workflow

def main():
 for stream in (sys.stdout,sys.stderr):
  try:stream.reconfigure(encoding='utf-8')
  except (AttributeError,ValueError):pass
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 c=sub.add_parser('check');c.add_argument('--root',required=True);c.add_argument('--artifact',action='append',required=True);c.add_argument('--revision',type=int,required=True)
 s=sub.add_parser('status');s.add_argument('--state',required=True)
 t=sub.add_parser('text');t.add_argument('file');t.add_argument('--profile',default='conversation_summary');t.add_argument('--candidate')
 w=sub.add_parser('wizard');w.add_argument('--root',required=True);w.add_argument('--state',required=True);w.add_argument('--artifact',action='append',required=True)
 f=sub.add_parser('profiles');f.add_argument('--store',required=True);f.add_argument('--import-file')
 r=sub.add_parser('resume');r.add_argument('--state',required=True)
 m=sub.add_parser('map');m.add_argument('--root',default='.');m.add_argument('--name');m.add_argument('--doc',default='docs/PROJECT-MAP.md');m.add_argument('--data',default='.kyper/project-map.json')
 m.add_argument('--write',action='store_true');m.add_argument('--check',action='store_true');m.add_argument('--json',dest='as_json',action='store_true');m.add_argument('--memory',action='store_true')
 m.add_argument('--graph',action='store_true',help='print the node/edge graph instead of the map summary')
 m.add_argument('--graph-format',choices=('json','mermaid','dot','graphml','tsv'),default='json')
 m.add_argument('--max-nodes',type=int,default=None)
 o=sub.add_parser('setup');o.add_argument('--root');o.add_argument('--state-dir');o.add_argument('--json',dest='as_json',action='store_true')
 ro=sub.add_parser('roles');ro.add_argument('--catalog');ro.add_argument('--json',dest='as_json',action='store_true');ro.add_argument('--export',metavar='ROLE')
 pl=sub.add_parser('plan');pl.add_argument('--state',required=True);pl.add_argument('--catalog');pl.add_argument('--json',dest='as_json',action='store_true')
 cp=sub.add_parser('component');cp.add_argument('id');cp.add_argument('--name',required=True);cp.add_argument('--catalog');cp.add_argument('--param',action='append',default=[]);cp.add_argument('--json',dest='as_json',action='store_true')
 ex=sub.add_parser('export');ex.add_argument('--host',choices=('claude','cursor','codex','gemini','copilot','generic'));ex.add_argument('--out');ex.add_argument('--role',action='append',default=[]);ex.add_argument('--catalog');ex.add_argument('--check',action='store_true');ex.add_argument('--list-hosts',action='store_true');ex.add_argument('--json',dest='as_json',action='store_true')
 a=p.parse_args()
 stale=[]
 if a.command=='resume':
  from .interactive import resume
  result=resume(a.state)
 elif a.command=='setup':
  from .onboarding import checklist
  result=checklist(a.root,state_dir=a.state_dir)
 elif a.command=='roles':
  from . import catalog as catalog_mod
  loaded=catalog_mod.load(a.catalog)
  if a.export:
   result={'role':a.export,'card':catalog_mod.export_role_card(catalog_mod.role(loaded,a.export))}
  else:
   result={'catalog':loaded,'digest':catalog_mod.digest(loaded),'markdown':catalog_mod.render_markdown(loaded)}
 elif a.command=='export':
  from . import catalog as catalog_mod
  from . import hosts
  loaded=catalog_mod.load(a.catalog)
  if a.list_hosts:
   result=hosts.capabilities()
  else:
   if not a.host:raise ValueError('Choose --host or use --list-hosts')
   if a.check:
    if not a.out:raise ValueError('--check requires --out')
    result=hosts.check(a.host,loaded,a.out,role_ids=a.role or None)
    stale=[item['path'] for item in result['stale']]
   else:
    if not a.out:raise ValueError('--out is required')
    result=hosts.write(a.host,loaded,a.out,role_ids=a.role)
   result['capabilities']=hosts.host(a.host)
 elif a.command=='plan':
  from .workflow import Workflow
  from . import plan as plan_mod
  from . import catalog as catalog_mod
  w=Workflow(a.state,catalog=catalog_mod.load(a.catalog))
  model=w.plan()
  result={'plan':model,'digest':plan_mod.digest(model),'markdown':plan_mod.render_markdown(model)}
 elif a.command=='component':
  from . import catalog as catalog_mod
  loaded=catalog_mod.load(a.catalog)
  template=catalog_mod.component(loaded,a.id)
  params={}
  for pair in a.param:
   if '=' not in pair: raise ValueError('Parameters use key=value')
   key,value=pair.split('=',1)
   spec=template['params'].get(key,{})
   params[key]=[item for item in value.split(',') if item] if spec.get('type')=='paths' and ',' in value else value
  rendered=catalog_mod.instantiate(loaded,a.id,name=a.name,params=params)
  result={'task':rendered,'preview':True,
          'note':'Not added. Pass these fields to Workflow.add_task in the specification stage.'}
 elif a.command=='map':
  from . import structure
  project=structure.scan(a.root,name=a.name)
  if a.graph:
   model=structure.graph(project,max_nodes=a.max_nodes)
   if a.graph_format=='json':result=model
   elif a.graph_format=='mermaid':result={'mermaid':'\n'.join(structure.render_graph_mermaid(project,max_nodes=a.max_nodes))}
   elif a.graph_format=='dot':result={'dot':structure.render_graph_dot(project)}
   elif a.graph_format=='graphml':result={'graphml':structure.render_graph_graphml(project)}
   else:result={'tsv':structure.render_graph_tsv(project)}
   print(json.dumps(result,ensure_ascii=False,indent=2));return
  document=structure.render_markdown(project)
  payload=structure.render_json(project)
  exports=structure.render_graph_exports(project)
  doc_path,data_path=Path(a.root)/a.doc,Path(a.root)/a.data
  if a.write:
   doc_path.parent.mkdir(parents=True,exist_ok=True);doc_path.write_text(document,encoding='utf-8')
   data_path.parent.mkdir(parents=True,exist_ok=True);data_path.write_text(payload,encoding='utf-8')
   for relative,text in exports.items():
    target=Path(a.root)/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8')
  if a.check:
   expected=[(doc_path,document),(data_path,payload)]+[(Path(a.root)/relative,text) for relative,text in exports.items()]
   stale=[str(path) for path,text in expected if not path.is_file() or path.read_text(encoding='utf-8')!=text]
  if a.as_json:result=project
  else:
   result={'root':project['root'],'files':len(project['files']),'edges':len(project['edges']),
           'areas':sorted(project['areas']),'doc':str(doc_path),'data':str(data_path),
           'written':a.write,'stale':stale}
   result['graph']={'nodes':structure.graph(project)['stats']['nodes'],'edges':len(project['edges']),
                    'exports':sorted(exports)}
   if a.memory:result['memory']=structure.memory_payload(project,doc_path=a.doc)
   if a.write:result['document_bytes']=len(document.encode('utf-8'))
 elif a.command=='profiles':
  from .profiles import load_profiles,save_profiles,import_profiles
  old=load_profiles(a.store) if Path(a.store).exists() else ()
  if a.import_file:
   profiles=import_profiles(Path(a.import_file).read_text(encoding="utf-8"))
   save_profiles(a.store,profiles,expected_revisions={p.profile_id:p.profile_revision for p in old} if Path(a.store).exists() else None)
  else: profiles=old
  result={'profiles':[p.to_dict() for p in profiles],'validation':'schema_only','host_validation':'not_run'}
 elif a.command=='wizard':
  from .interactive import run
  result=run(state=a.state,root=a.root,artifacts=a.artifact)
 elif a.command=='check':
  r=Review(a.root,a.artifact,a.revision);r.syntax();result=r.gate(['code'])
 elif a.command=='status':
  if not Path(a.state).exists():raise ValueError('State not found')
  w=Workflow(a.state);result={'state':w.data['state'],'revision':w.data['revision'],'events':w.data['events']}
 else:
  from .editorial import review
  result=review(Path(a.file).read_text(encoding="utf-8"),a.profile,candidate=Path(a.candidate).read_text(encoding="utf-8") if a.candidate else None)
 if a.command=='setup' and not a.as_json:
  print(result['prompt']);print();print(json.dumps({'ready':result['ready'],'needs_input':result['needs_input']},ensure_ascii=False,indent=2))
 else:
  print(json.dumps(result,ensure_ascii=False,indent=2))
 if stale:raise SystemExit(1)
if __name__=='__main__':main()
