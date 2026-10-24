# -*- coding: utf-8 -*-
import json
import os
import time


def _norm(file_path):
    return os.path.normcase(os.path.abspath(file_path))


class ModeStore:
    """파일 경로 -> {'line', 'time'} 저장소. put/remove 마다 파일에 즉시 쓴다."""

    def __init__(self, path, limit=500):
        self._path = path
        self._limit = limit
        self._data = self._load()

    def _load(self):
        try:
            with open(self._path, 'r', encoding='utf-8') as f:
                raw = f.read()
        except FileNotFoundError:
            return {}
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(obj, dict):
            return {}
        out = {}
        for k, v in obj.items():
            if (isinstance(v, dict) and isinstance(v.get('line'), int)
                    and isinstance(v.get('time'), (int, float))):
                out[k] = {'line': v['line'], 'time': float(v['time'])}
        return out

    def _save(self):
        d = os.path.dirname(self._path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self._path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False)
        os.replace(tmp, self._path)

    def get(self, file_path):
        e = self._data.get(_norm(file_path))
        return dict(e) if e is not None else None

    def put(self, file_path, line, now=None):
        if now is None:
            now = time.time()
        key = _norm(file_path)
        self._data.pop(key, None)
        self._data[key] = {'line': int(line), 'time': float(now)}
        if len(self._data) > self._limit:
            # 시각 오름차순 제거. 같은 시각이면 삽입 순서(오래된 것)가 먼저다(sorted 는 안정 정렬).
            order = sorted(self._data, key=lambda k: self._data[k]['time'])
            for k in order[:len(self._data) - self._limit]:
                del self._data[k]
        self._save()

    def remove(self, file_path):
        if self._data.pop(_norm(file_path), None) is not None:
            self._save()
