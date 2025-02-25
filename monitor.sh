#!/bin/sh

ml tools/miniconda3
conda activate monit
python3 monitor.py
