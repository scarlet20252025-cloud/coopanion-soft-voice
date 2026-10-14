"""CLI wrapper for the installer shipped inside the standalone World package."""
import argparse
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('voice_bubble_installer',Path(__file__).resolve().parents[1]/'world/src/install_bubble_bridge.py')
helper=importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
MARKER=helper.MARKER
HOOKS=helper.HOOKS
patched=helper.patched
install_bridge=helper.install_bridge

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--desktop-pet',required=True)
    parser.add_argument('--restore',action='store_true')
    args=parser.parse_args()
    print('Bubble bridge ready:',install_bridge(args.desktop_pet,args.restore))
