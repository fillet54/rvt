import os
import sys
import asyncio
import mimetypes
import signal
import tornado.web
import tornado.websocket
import tornado.options
import tornado.httpserver

import click
import json

from jinja2 import Environment, FileSystemLoader
from heroicons.jinja import heroicon_outline, heroicon_solid

from .routes import app_routes
from .handlers.errors import NotFoundHandler

def platform_specific_config():
    'Platform specific configuration/setup'
    # See https://github.com/tornadoweb/tornado/issues/2804
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Patch MIME Types for Windows. This could be done in Windows globally
    # See: https://stackoverflow.com/questions/3442607/mime-types-in-the-windows-registry/3452261#3452261
    mimetypes.add_type('application/javascript', '.js')

def setup_jinja_env(settings):
    env = Environment(loader=FileSystemLoader(settings.get('template_path', [])))
    env.globals.update({ 
        'heroicon_outline': heroicon_outline,
        'heroicon_solid': heroicon_solid,
        'settings': settings,
        'STATIC_URL': settings.get('static_url_prefix', '/static/'),
        'json': json,
    })
    settings['jinja_env'] = env


class Application(tornado.web.Application):
    is_closing = False

    def signal_handler(self, signum, frame):
        self.is_closing = True

    def try_exit(self):
        if self.is_closing:
            # clean up here
            tornado.ioloop.IOLoop.instance().stop()


def start_app(routes, settings):
    application = Application(routes, **settings)
    signal.signal(signal.SIGINT, application.signal_handler)
    application.listen(settings['port'])
    tornado.ioloop.PeriodicCallback(application.try_exit, 100).start()
    tornado.ioloop.IOLoop.instance().start()


@click.command()
@click.option('--port', default=8087, type=int)
def cli(port):
    settings = {
        'port': port,
        'static_path': os.path.join(os.path.dirname(__file__), 'static'),
        'static_url_prefix': '/static/',
        'template_path': os.path.join(os.path.dirname(__file__), 'templates'),
        'gzip': True,
        'debug': True,
        'default_handler_class': NotFoundHandler,
    }
    
    platform_specific_config()
    setup_jinja_env(settings)
    
    click.echo(f"Starting " + click.style("Automation-v3", fg='blue') + f" on port {port}")
    start_app(app_routes, settings)


