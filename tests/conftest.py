# -*- coding: utf-8 -*-
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (os.path.join(ROOT, 'lib'), ROOT):
    if p in sys.path:
        sys.path.remove(p)
    sys.path.insert(0, p)
