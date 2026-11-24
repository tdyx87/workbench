# gunicorn 配置
import os

# 日志目录默认落在项目目录内，可用 WORKBENCH_LOG_DIR 覆盖
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.environ.get("WORKBENCH_LOG_DIR") or BASE_DIR

bind = "0.0.0.0:8000"
workers = 2
threads = 2
timeout = 60
accesslog = os.path.join(LOG_DIR, "gunicorn_access.log")
errorlog = os.path.join(LOG_DIR, "gunicorn_error.log")
loglevel = "info"
proc_name = "workbench"
