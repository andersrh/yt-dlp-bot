import logging

from pyrogram import filters
from pyrogram.handlers import MessageHandler
from yt_shared.rabbit import get_rabbitmq
from yt_shared.utils.tasks.tasks import create_task

from bot.core.bot import VideoBot
from bot.core.callbacks import TelegramCallback
from bot.core.tasks.ytdlp import YtdlpNewVersionNotifyTask
from bot.core.workers.manager import RabbitWorkerManager


class BotLauncher:
    """Bot launcher which parses configuration file, creates and starts the bot."""

    REGEX_NOT_START_WITH_SLASH = r'^[^/]'

    def __init__(self) -> None:
        """Constructor."""
        self._log = logging.getLogger(self.__class__.__name__)
        self._bot = VideoBot()
        self._rabbit_mq = get_rabbitmq()
        self._rabbit_worker_manager = RabbitWorkerManager(bot=self._bot)

    async def run(self) -> None:
        """Run bot."""
        await self._setup_rabbit()
        self._setup_handlers()
        await self._start_bot()

    def _setup_handlers(self) -> None:
        cb = TelegramCallback()
        self._bot.add_handler(
            MessageHandler(
                cb.on_start,
                filters=filters.user(list(self._bot.allowed_users.keys()))
                & filters.command(['start', 'help']),
            ),
        )
        self._bot.add_handler(
            MessageHandler(
                cb.on_message,
                filters=(
                    filters.regex(self.REGEX_NOT_START_WITH_SLASH)
                    & (
                        filters.user(list(self._bot.allowed_users.keys()))
                        | filters.chat(list(self._bot.allowed_users.keys()))
                    )
                ),
            ),
        )

    async def _setup_rabbit(self) -> None:
        task_name = f'Setup RabbitMQ Task ({self._rabbit_mq.__class__.__name__})'
        await create_task(
            self._rabbit_mq.register(),
            task_name=task_name,
            logger=self._log,
            exception_message='Task "%s" raised an exception',
            exception_message_args=(task_name,),
        )

    async def _start_tasks(self) -> None:
        await self._rabbit_worker_manager.start_workers()

        task_name = YtdlpNewVersionNotifyTask.__class__.__name__
        create_task(
            YtdlpNewVersionNotifyTask(bot=self._bot).run(),
            task_name=task_name,
            logger=self._log,
            exception_message='Task "%s" raised an exception',
            exception_message_args=(task_name,),
        )

    async def _start_bot(self) -> None:
        """Start telegram bot and related processes."""
        await self._bot.start()

        self._log.info('Starting "%s" bot', (await self._bot.get_me()).first_name)
        await self._bot.send_startup_message()
        await self._start_tasks()
        await self._bot.run_forever()
