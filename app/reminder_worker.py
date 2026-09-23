"""An explicitly started reminder process. Generates internal tasks; sends no messages."""
import argparse
import logging
import threading
from .customer_service import tick_reminders

log=logging.getLogger(__name__)


def run(*,once=False,stop_event=None):
    stop_event=stop_event or threading.Event()
    while not stop_event.is_set():
        result=tick_reminders()
        if result['errors']:log.warning('客户提醒生成需要检查：%s 家门店存在错误',len(result['errors']))
        if once or stop_event.wait(60):return result


def main():
    parser=argparse.ArgumentParser(description='huakangos 内部服务提醒任务进程')
    parser.add_argument('--once',action='store_true',help='只检查一次已启用规则及资料变化')
    args=parser.parse_args()
    try:run(once=args.once)
    except KeyboardInterrupt:pass


if __name__=='__main__':main()
