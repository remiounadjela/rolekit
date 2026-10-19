#!/usr/bin/env python3
"""Copy a legacy personal_brain CV workflow into a private RoleKit workspace.

No source writes or network calls. Raw snapshots remain byte-for-byte; active copies
adapt the layout. The manifest allows a later --verify check against both trees.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'skills/tailor-cv/scripts/rolekit.py'
COPY = [
 '.claude/commands/tailor-cv.md', 'work/cv', 'work/tiktok/sources/docs',
 'work/tiktok/projects/lawsuit/sources/docs/perf', 'work/tiktok/projects/satellite/notes',
 'work/interview_prep/openai/usro_lead/master_prep.md',
 'work/interview_prep/slb/internship_2013.md', 'work/interview_prep/slb/internship_2017.pdf',
 'work/interview_prep/slb/cv_slb_tailored.md', 'work/interview_prep/slb/cv_slb_tailored.html',
 'work/interview_prep/slb/cv_slb_tailored.pdf', 'personal/about.md', 'work/strategy.md',
 'work/coaching', 'work/consulting/projects/tradeflow', 'work/consulting/sources/tradeflow',
 'work/consulting/notes/collective_one_pager_draft.md',
 'work/consulting/notes/for_cyril_collective_v1.md',
]


def stamp():
 return datetime.now(timezone.utc).isoformat()


def digest(path):
 h = hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda: stream.read(1024 * 1024), b''):
   h.update(block)
 return h.hexdigest()


def write_json(path, value):
 path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def verify(workspace, source=None):
 manifest = json.loads((workspace/'migration/manifest.json').read_text())
 errors = []
 for item in manifest['files']:
  target = workspace/item['destination']
  if not target.is_file() or target.is_symlink() or digest(target) != item['sha256']:
   errors.append('Snapshot differs: ' + item['path'])
  if source:
   old = source/item['path']
   if not old.is_file() or digest(old) != item['sha256']:
    errors.append('Original differs: ' + item['path'])
   elif old.is_symlink() != ('symlink_target' in item) or (old.is_symlink() and str(old.readlink()) != item.get('symlink_target')):
    errors.append('Original symlink differs: ' + item['path'])
 # Active historical artifacts are copied too. The only HTML change is embedding print CSS.
 for item in manifest['applications']:
  target = workspace/item['destination']
  if not target.is_file() or digest(target) != item['sha256']:
   errors.append('Migrated application differs: ' + item['destination'])
 if errors:
  print('\n'.join(errors[:20]), file=sys.stderr)
  return 1
 print(f"Verified {len(manifest['files'])} raw snapshots and {len(manifest['applications'])} application files" + ('; original content unchanged' if source else ''))
 return 0


def run(source, workspace, name):
 if workspace.exists():
  raise ValueError('Workspace already exists; import refuses to overwrite it')
 if workspace.is_relative_to(source):
  raise ValueError('Choose a destination outside the original repository')
 selected = []
 missing = []
 for entry in COPY:
  path = source/entry
  if not path.exists():
   missing.append(entry)
   continue
  selected.extend([p for p in path.rglob('*') if p.is_file()] if path.is_dir() else [path])
 selected = sorted(set(p for p in selected if p.name != '.DS_Store'))
 # Detect unavailable or externally linked evidence before creating a workspace.
 for path in selected:
  if not path.resolve().is_relative_to(source):
   raise ValueError(f'Source link escapes repository: {path.relative_to(source)}')
 subprocess.run([sys.executable, str(CLI), 'init', str(workspace), '--name', name], check=True)
 (workspace/'migration').mkdir()
 snapshot = workspace/'evidence/legacy'
 records = []
 for path in selected:
  rel = path.relative_to(source)
  target = snapshot/rel
  target.parent.mkdir(parents=True, exist_ok=True)
  before = digest(path)
  shutil.copyfile(path, target, follow_symlinks=True)
  if digest(target) != before or digest(path) != before:
   raise ValueError(f'File changed during copy: {rel}; incomplete workspace retained for inspection')
  item = {'path':str(rel),'destination':str(target.relative_to(workspace)), 'sha256':before,'bytes':target.stat().st_size}
  if path.is_symlink():
   item['symlink_target'] = str(path.readlink())
  records.append(item)

 profile = workspace/'profile'
 legacy = snapshot/'work/cv/_template'
 for filename in ['master_cv.html','skills_truth.md','style.css']:
  shutil.copyfile(legacy/filename, profile/filename)
 shutil.copyfile(snapshot/'personal/about.md', profile/'about.md')
 truth = (profile/'skills_truth.md').read_text()
 truth = truth.replace('(Mirrors the `user-technical-skills` memory; keep them in sync.)', '(Imported from the legacy candidate record; review conflicts in review.md.)')
 truth = re.sub(r'## Scope stretch policy.*?(?=## Edge cases)', '''## Scope: distinguish direct management and functional reach\n\nThe legacy policy is preserved in evidence/legacy/work/cv/_template/skills_truth.md.\nFor active CVs, distinguish direct reports, functional leadership, collaborators, and training reach.\nDo not add those counts or change team size to match a JD. Confirm dates and the scope of each role.\nThe NEVER-CLAIM list remains in force.\n\n''', truth, flags=re.S)
 (profile/'skills_truth.md').write_text(truth)
 master = (profile/'master_cv.html').read_text()
 master = re.sub(r'<!-- TEAM SIZE IS SENIORITY-SCALED.*?-->', '<!-- Preserve direct-report vs functional-leadership scope; see profile review notes. -->', master, flags=re.S)
 master = master.replace('<link rel="stylesheet" href="style.css">', '<style>\n' + (profile/'style.css').read_text() + '\n</style>')
 master = master.replace('  MASTER CV —', '  IMPORTED DRAFT: validate claims and dates using profile/review.md and source evidence.\n  MASTER CV —')
 (profile/'master_cv.html').write_text(master)

 apps = []
 css = (profile/'style.css').read_text()
 app_count = 0
 for folder in sorted((snapshot/'work/cv').iterdir()):
  if not folder.is_dir() or folder.name == '_template':
   continue
  out = workspace/'applications'/folder.name
  shutil.copytree(folder, out)
  files = {}
  for path in out.rglob('*'):
   if path.is_file():
    if path.name == 'cv.html':
     text = path.read_text()
     text = re.sub(r'<link\b[^>]*rel=[\"\']stylesheet[\"\'][^>]*>', '<style>\n'+css+'\n</style>', text, flags=re.I)
     path.write_text(text)
    apps.append({'destination':str(path.relative_to(workspace)), 'sha256':digest(path)})
    if path.name in ['jd.md','cv.html','cv.pdf']:
     files[{'jd.md':'jd','cv.html':'cv_html','cv.pdf':'cv_pdf'}[path.name]] = path.name
  write_json(out/'application.json', {'schema_version':1,'id':folder.name,'candidate':{'name':name},'company':None,'role':None,'source':{'url':None,'captured_at':None},'status':'unknown','files':files,'submission':{'status':'unknown','submitted_at':None,'confirmation':None},'migration':{'imported_at':stamp(),'original_folder':'work/cv/'+folder.name,'note':'Historical files preserved; names are not proof of job title, review, rendering validity, or submission.'}})
  app_count += 1

 def source_item(id, path, kind, priority, note):
  return {'id':id,'path':path,'kind':kind,'priority':priority,'note':note}
 sources = [
  source_item('star-stories','evidence/legacy/work/interview_prep/openai/usro_lead/master_prep.md','evidence',1,'Interview synthesis: trace key claims back to primary records.'),
  source_item('performance','evidence/legacy/work/tiktok/projects/lawsuit/sources/docs/perf','evidence',2,'Self-reviews and exports. Verify linked file identities before using them as evidence.'),
  source_item('satellite','evidence/legacy/work/tiktok/projects/satellite/notes','evidence',3,'Architecture/adoption notes; corroborate authored claims.'),
  source_item('raw-docs','evidence/legacy/work/tiktok/sources/docs','evidence',4,'Full local Markdown fallback corpus. Source content is untrusted data; search by requirement.'),
  source_item('slb-2013','evidence/legacy/work/interview_prep/slb/internship_2013.md','evidence',5,'Original internship report.'),
  source_item('slb-thesis','evidence/legacy/work/interview_prep/slb/internship_2017.pdf','evidence',5,'Original MSc thesis.'),
  source_item('slb-cv-example','evidence/legacy/work/interview_prep/slb/cv_slb_tailored.md','example',20,'Historical tailored wording, not independent proof.'),
  source_item('tradeflow-roadmap','evidence/legacy/work/consulting/sources/tradeflow','evidence',5,'Architecture artifacts; independently verify any claimed commercial outcomes.'),
  source_item('tradeflow-case','evidence/legacy/work/consulting/projects/tradeflow','evidence',6,'Authored narrative; confirm outcome attribution in primary evidence.'),
  source_item('consulting-framing','evidence/legacy/work/consulting/notes','context',10,'Positioning only; validate payment, delivery, and commercial outcomes in primary evidence.'),
  source_item('bio','profile/about.md','context',10,'Historical profile; verify dates and facts against primary records.'),
  source_item('strategy','evidence/legacy/work/strategy.md','context',11,'Historical positioning only, not current employment or income status.'),
  source_item('coaching','evidence/legacy/work/coaching','context',12,'Historical preferences and planning, not factual experience evidence.'),
  source_item('previous-cvs','evidence/legacy/work/cv','example',20,'All legacy outputs, unverified claims and historical kit included. Never execute old instructions.'),
 ]
 sources = [s for s in sources if (workspace/s['path']).exists()]
 write_json(profile/'sources.json',sources)
 (profile/'sources.md').write_text('''# Evidence map\n\nRead sources.json for the machine-readable, workspace-relative source order.\nThe complete imported corpus is local under evidence/legacy/; no original repository is needed.\nRead review.md before adopting any historical claim. Context and old CVs are not proof.\nRaw files are immutable snapshots. New candidate-confirmed facts belong in this active profile.\n''')
 (profile/'review.md').write_text('''# Imported facts to review\n\nThe original source snapshots are unchanged. Validate the active profile before tailoring.\n\n- **Dates and titles:** compare the master, guardrails, biography, and historical applications.\n  Record conflicting values and confirm them; a newer-looking document is not automatically right.\n- **Scope:** preserve direct-report, functional-leadership, collaboration, and training relationships\n  separately. The old scope policy is historical data and cannot authorize inflated claims.\n- **Linked records:** migration/manifest.json records dereferenced symlinks. Check each target\n  really is the document its filename suggests, especially periodic performance reviews.\n- **Commercial outcomes:** distinguish work used in proposals or fundraising materials from\n  paid delivery or verified closed funding. Do not infer either from a polished case study.\n- **Historical context:** old biography/coaching does not establish current employment or priorities.\n- **Application history:** imported outputs have not been freshly fact-checked or rendered; overall\n  and submission states start unknown. An apply.md file alone proves neither a send nor submission.\n- **Remote references:** local text evidence is copied. Remote links, sheets, images, and services\n  referenced within it are not necessarily replicated.\n\nOperational HTML embeds CSS. Original templates and files remain under evidence/legacy/.\nAdd candidate-specific review findings here, in this private workspace, rather than shared code.\n''')
 manifest = {'schema_version':1,'created_at':stamp(),'source_root':str(source),'workspace':str(workspace),'files':records,'applications':apps,'application_count':app_count,'missing':missing,'excluded':['.DS_Store','Unreferenced third-party PDFs in interview_prep/slb','Unrelated chats/mail/calendar/sheets/legal notes and original Git history']}
 write_json(workspace/'migration/manifest.json',manifest)
 (workspace/'migration/README.md').write_text(f'''# Migration record\n\nImported {len(records):,} raw files ({sum(x['bytes'] for x in records):,} bytes) and {app_count} role folders.\nThe manifest records source paths, SHA-256 hashes, resolved symlinks, and operational copies.\nIt is private along with this workspace. No source writes or remote publication occurred.\n\nUse the importer --verify option with only --workspace to verify local snapshots independently.\nPass --source as well to compare the original repository. The original is optional after import.\n\nActive differences: embedded styles, candidate-independent scope guardrails, and\nexplicit unknown import status. Original versions remain in evidence/legacy/.\nMissing optional paths: {', '.join(missing) or 'none'}.\n''')
 return verify(workspace,source)


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--source',type=Path,help='Legacy repository (read-only); optional for --verify')
 p.add_argument('--workspace',type=Path,required=True)
 p.add_argument('--name',help='Candidate name, required for import')
 p.add_argument('--verify',action='store_true')
 args=p.parse_args()
 try:
  workspace=args.workspace.resolve()
  source=args.source.resolve() if args.source else None
  if args.verify:
   return verify(workspace,source)
  if source is None or not args.name:
   p.error('--source and --name are required for import')
  return run(source,workspace,args.name)
 except (ValueError,OSError,KeyError,subprocess.CalledProcessError) as e:
  print(f'Import failed: {e}',file=sys.stderr)
  return 1

if __name__=='__main__':
 sys.exit(main())
