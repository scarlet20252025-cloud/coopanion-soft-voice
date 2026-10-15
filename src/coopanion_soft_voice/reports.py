"""Local report library and explicit, redacted GitHub reporting. Never loads a TTS model."""
import argparse
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import time
import uuid

from . import diagnostics, issue_reporting

CODES = {
    'manual': '手动检查', 'worker_error': '语音进程异常', 'worker_exit': '语音进程意外退出',
    'startup_timeout': '语音加载超时', 'speech_timeout': '语音播放超时',
    'protocol_error': '语音通信异常', 'memory_guard': '内存保护阻止加载',
    'slow_synthesis': '连续两次合成慢于实时', 'playback_underflow': '连续两次播放欠载',
}
MAX_REPORTS = 20
COOLDOWN = 86400


def atomic(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    os.replace(temporary, path)


class Reports:
    def __init__(self, runtime, data_dir, world_version=None):
        self.world_version=world_version
        self.runtime, self.data = Path(runtime).resolve(), Path(data_dir).resolve()
        self.root = self.data / 'diagnostics'
        if self.root.is_symlink() or self.root.resolve() != self.root:
            raise ValueError('Diagnostic folder must be a physical local directory')
        self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, report_id):
        if not isinstance(report_id, str) or not re.fullmatch(r'[0-9a-f]{32}', report_id):
            raise ValueError('Invalid report ID')
        folder = self.root / report_id
        if folder.resolve() != folder or folder.is_symlink():
            raise ValueError('Report folder must not redirect outside local diagnostics')
        return folder

    def records(self, limit=MAX_REPORTS):
        rows = []
        for folder in self.root.iterdir():
            if re.fullmatch(r'[0-9a-f]{32}', folder.name) and folder.is_dir() and not folder.is_symlink():
                if folder.resolve() != folder:
                    continue
                row = diagnostics.read_json(folder / 'record.json')
                if row.get('id') == folder.name:
                    rows.append(row)
        return sorted(rows, key=lambda row: row.get('created', 0), reverse=True)[:limit]

    def record(self, report_id):
        folder = self.folder(report_id)
        row = diagnostics.read_json(folder / 'record.json')
        if row.get('id') != report_id:
            raise ValueError('Report does not exist')
        return folder, row

    def archive(self, folder, row):
        name = row.get('archive', '')
        if not name or Path(name).name != name or not name.endswith('.zip'):
            raise ValueError('Invalid report archive')
        archive = folder / name
        if archive.resolve() != archive or not archive.is_file():
            raise ValueError('Report archive unavailable')
        return archive

    def list(self):
        return {'reports': self.records(), 'retention': MAX_REPORTS,
                'repository': 'https://github.com/' + issue_reporting.REPO + '/issues'}

    def collect(self, seconds=0, code='manual', automatic=False):
        if code not in CODES or seconds not in (0, 30, 60):
            raise ValueError('Invalid report request')
        now = time.time()
        if automatic:
            window=diagnostics.read_json(self.root/'auto-window.json')
            recent={key:value for key,value in window.items() if key in CODES and isinstance(value,(float,int)) and 0<=now-value<COOLDOWN}
            if code in recent or len(recent) >= 3:
                return {'skipped': True, 'reason': '相同问题 24 小时仅留一份；每天最多三份自动报告'}
            recent[code]=now
            atomic(self.root/'auto-window.json',recent)
        report_id = uuid.uuid4().hex
        folder = self.folder(report_id)
        folder.mkdir()
        # Collector output is machine-readable only at this module's final boundary.
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                archive = diagnostics.collect(self.runtime, folder, self.data, seconds=seconds, world_version=self.world_version)
            report, _ = issue_reporting.read_package(archive)
            analysis = CODES[code] + '（自动检测，仅记录现象，根因待核实）' if automatic else CODES[code] + '（用户主动采集，根因待核实）'
            analysis += '\n\n采集不运行额外合成；请核对报告时间和最近播放时间，历史读数不能当作当前复现。'
            analysis_file = folder / 'analysis.md'
            analysis_file.write_text(analysis, encoding='utf-8')
            with contextlib.redirect_stdout(io.StringIO()):
                result, fallback = issue_reporting.run(archive, analysis_file)
            row = {'id': report_id, 'created': now, 'atUtc': report['createdAtUtc'], 'code': code,
                   'title': CODES[code], 'automatic': automatic, 'archive': fallback.name,
                   'summary': report['summary'], 'submission': result}
            atomic(folder / 'record.json', row)
            # Only this module's UUID folders with valid own records can be pruned.
            older = self.records(limit=None)
            if len(older) > MAX_REPORTS:
                for candidate in older[MAX_REPORTS:]:
                    if candidate['id'] != report_id:
                        old = self.folder(candidate['id'])
                        if old.resolve().parent != self.root:
                            raise ValueError('Invalid diagnostic retention target')
                        shutil.rmtree(old)
            return {'report': row}
        except Exception:
            # Leave a diagnostic failure marker; do not upload exception text.
            atomic(folder / 'collection-failed.json', {'at': now, 'code': code})
            raise

    def detail(self, report_id):
        folder, row = self.record(report_id)
        report, files = issue_reporting.read_package(self.archive(folder, row))
        # Full sanitized report is available inside ZIP; UI keeps the response bounded.
        last = report.get('samples', [])[-1:]
        return {'report': row, 'snapshot': {key: report.get(key) for key in
                ('createdAtUtc', 'installedPythonPackageVersion', 'portableVersion', 'worldVersion',
                 'hardware', 'runtime', 'summary', 'limitations')},
                'sample': last[0] if last else None,
                'perf': files.get('perf.log', b'').decode('utf-8')[-10000:]}

    def export(self, report_id):
        folder, row = self.record(report_id)
        archive = self.archive(folder, row)
        if archive.stat().st_size > 5 * 1024**2:
            raise ValueError('Report ZIP exceeds export limit')
        return {'filename': 'voice-diagnostics-' + report_id[:8] + '.zip',
                'base64': base64.b64encode(archive.read_bytes()).decode('ascii')}

    def submit(self, report_id, authorized=False, automatic=False):
        if authorized is not True:
            raise ValueError('Public issue submission requires the user option or explicit action')
        folder, row = self.record(report_id)
        if row.get('submission', {}).get('submitted'):
            return {'report': row}
        if automatic and time.time() - row.get('lastAttempt', 0) < COOLDOWN:
            return {'report': row, 'skipped': True}
        row['lastAttempt'] = time.time()
        atomic(folder / 'record.json', row)  # No repeated requests after a crash/offline restart.
        with contextlib.redirect_stdout(io.StringIO()):
            result, archive = issue_reporting.run(self.archive(folder, row), folder / 'analysis.md',
                                                  submit=True, skip_duplicate=automatic)
        row.update(submission=result, archive=archive.name)
        atomic(folder / 'record.json', row)
        return {'report': row}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', required=True); p.add_argument('--data-dir', required=True)
    p.add_argument('--world-version')
    p.add_argument('action', choices=('list', 'collect', 'detail', 'export', 'submit'))
    p.add_argument('--id'); p.add_argument('--seconds', type=int, default=0)
    p.add_argument('--code', default='manual'); p.add_argument('--automatic', action='store_true')
    p.add_argument('--authorized', action='store_true')
    a = p.parse_args(); reports = Reports(a.runtime, a.data_dir, a.world_version)
    if a.action == 'list': result = reports.list()
    elif a.action == 'collect': result = reports.collect(a.seconds, a.code, a.automatic)
    elif a.action == 'detail': result = reports.detail(a.id)
    elif a.action == 'export': result = reports.export(a.id)
    else: result = reports.submit(a.id, a.authorized, a.automatic)
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))


if __name__ == '__main__': main()
