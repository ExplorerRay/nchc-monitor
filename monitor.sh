#!/bin/sh

ml tools/miniconda3
conda activate monit
username=$(whoami)
/home/${username}/.conda/envs/monit/bin/python3 /home/${username}/nchc-monitor/monitor.py
