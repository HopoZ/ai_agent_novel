"""进程级单例：NovelAgent、命名日志。"""

import logging

from agents.novel import NovelAgent

logger = logging.getLogger("webapp.backend.server")

agent = NovelAgent()
