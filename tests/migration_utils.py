from alembic import command
from alembic.config import Config


def migrate(url):
    config = Config('alembic.ini')
    config.set_main_option('sqlalchemy.url', url)
    command.upgrade(config, 'head')
