# nchc-monitor
NCHC F1 node monitor script

## Usage
1. 將 monitor.py 中的 MATTERMOST_WEBHOOK_URL 設定為跟 Mattermost 管理者要的 Webhook URL

2. 處理環境問題，`conda env create -f conda_env.yml`

3. 然後使用 `crontab -e`

```
* * * * * /home/${username}/nchc-monitor/monitor.sh
```
