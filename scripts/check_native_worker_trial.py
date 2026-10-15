"""Model-free C++ protocol and Unicode clause parity; not a GPU/voice test."""
import argparse
import json
from pathlib import Path
import random
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from coopanion_soft_voice.speech_text import split_speech_text


def check(executable):
    about=subprocess.run([str(executable),'--about'],capture_output=True,text=True,encoding='utf-8',check=True)
    assert json.loads(about.stdout)['defaultAdopted'] is False
    samples=['','\n\t\u3000','字'*32+'\n','这句话很短。','字'*100,'🙂'*45,'测试——这是后面的句子。'*10]
    rng=random.Random(44)
    chars='这里是中文和ABC123🙂。，！？,;:—…\n\t\u3000'
    samples.extend(''.join(rng.choice(chars) for _ in range(rng.randrange(200))) for _ in range(300))
    child=subprocess.run([str(executable),'--split-test'],input=''.join(json.dumps(s,ensure_ascii=False)+'\n' for s in samples),capture_output=True,text=True,encoding='utf-8',check=True)
    results=[json.loads(line) for line in child.stdout.splitlines()]
    assert len(results)==len(samples)
    for text,parts in zip(samples,results):
        assert parts==split_speech_text(text,32,24),repr(text)
    print(json.dumps({'ok':True,'unicodeCases':len(samples),'modelLoaded':False,'audioGenerated':False}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True)
    check(p.parse_args().exe.resolve())
