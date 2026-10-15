"""Build a small standalone diagnostic kit that also works with portable 0.4.11."""
import argparse,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def build(output):
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT/'src/coopanion_soft_voice/issue_reporting.py','scripts/issue_reporting.py')
        z.write(ROOT/'src/coopanion_soft_voice/gpu_memory.py','scripts/gpu_memory.py')
        z.write(ROOT/'src/coopanion_soft_voice/diagnostics.py','scripts/collect_diagnostics.py')
        for name in ('collect-diagnostics.ps1','find-coopanion.ps1','report_issue.py'):z.write(ROOT/'scripts'/name,'scripts/'+name)
        z.write(ROOT/'docs/DIAGNOSTICS.md','README.md');z.write(ROOT/'LICENSE','LICENSE')
        for name in ('AI_BUG_REPORTS.md','INSTALL_WITHOUT_MARKET.md'):z.write(ROOT/'docs'/name,name)
        z.writestr('collect-diagnostics.cmd','@echo off\r\npowershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\\collect-diagnostics.ps1" %*\r\npause\r\n')
    print(str(target.resolve()))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();build(a.output)
