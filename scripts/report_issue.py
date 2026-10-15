"""Compatibility entry for the installed reporter or standalone diagnostic kit."""
import argparse
from pathlib import Path
import sys
source=Path(__file__).resolve().parents[1]/'src'
if source.is_dir():sys.path.insert(0,str(source))
sys.path.insert(0,str(Path(__file__).resolve().parent))
try:
    from coopanion_soft_voice.issue_reporting import run
except ImportError:
    from issue_reporting import run

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--diagnostics',required=True);p.add_argument('--analysis')
    p.add_argument('--submit',action='store_true');p.add_argument('--issue-number',type=int)
    a=p.parse_args();run(a.diagnostics,a.analysis,a.submit,a.issue_number)
