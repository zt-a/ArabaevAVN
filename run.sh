#!/bin/bash
cd $(dirname $0)
python3 -m venv venv 2>/dev/null; source venv/bin/activate 2>/dev/null
pip install -q -r requirements.txt 2>/dev/null
python main.py
