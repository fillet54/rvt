
# This will be the main entry point for the framework for a test developer.
# It is not clear if this also will be the interface for programatic API
#
# It will provide the following features:
#
# 1. Find all tests in the .yml format. For now each test case is in a single
#    file named by its testcase number. This will force us to rely on the
#    manager to easily edit but I think thats okay.
#
# 2. Provide a web interface to read/run/modify/add test cases. This can provide
#    almost limitless possibilities for displaying and grouping. A few examples
#    could be.
#       - By requirement (single test case may test multiple requirements)
#       - By tag (a tag could be a subsystem or it can be arbitrary)
#       - Sorted by timestamp
#       - etc...
from automationv3.util import get_client_unique_id_generator
import sys
import asyncio
import os
import signal
import time
import json
import mimetypes

import tornado.web
import tornado.websocket
import tornado.options
import tornado.httpserver

import yaml
from yaml import safe_load, dump, Dumper
import os

from .framework import TestCase


class TestCaseRepository:
    def __init__(self, root_path, id_generator):
        self.root = root_path
        self.id_generator = id_generator

    def get(self, id=None):
        all = self.get_all()

        if id is None:
            return all.values()

        return all[id]

    def get_categories(self):
        def isdir(x): return os.path.isdir(os.path.join(self.root, x))
        return [name for name in os.listdir(self.root) if isdir(name)]

    def get_all(self):
        testcases = {}
        for root, dirs, files in os.walk(self.root):
            yaml_files = [name for name in files if name.endswith('.yaml')]
            for name in yaml_files:
                tc_path = os.path.join(root, name)
                with open(tc_path, 'r') as f:
                    tc = TestCase.load(f)
                    tc.path = root[(len(self.root) + 1):]
                    testcases[tc.id] = tc
        return testcases

    @staticmethod
    def get_testcase_fname(tc):
        return 'tc{:016X}.yaml'.format(tc.id)

    def create(self, relpath, id=None):
        if id is None:
            id = next(self.id_generator)

        tc = TestCase(id=id, steps=[''])
        fullpath = os.path.join(
            relpath, TestCaseRepository.get_testcase_fname(tc))

        if os.path.exists(os.path.join(self.root, fullpath)):
            raise ValueError("Test case already exists")

        self.save(relpath, tc)
        return tc

    def save(self, relpath, testcase):
        fullpath = os.path.join(
            self.root, relpath, TestCaseRepository.get_testcase_fname(testcase))

        with open(fullpath, 'w') as f:
            testcase.dump(f)


class BaseHandler(tornado.web.RequestHandler):

    @property
    def repo(self) -> TestCaseRepository:
        return self.settings['testcase_repo']


class NotFoundHandler(BaseHandler):
    def get(self):
        return self.render('404.html')


class HomeHandler(BaseHandler):
    def get(self):
        return self.render('home.html', heading_text='Dashboard')


class TestCaseHandler(BaseHandler):
    def get(self, id):
        testcase = self.repo.get(id=int(id, 16))
        return self.render('testcase.html', testcase=testcase)

    def post(self, id):
        cur_tc = self.repo.get(id=int(id, 16))
        new_tc = TestCase(
            id=int(id, 16),
            description=self.get_argument('description', cur_tc.description))

        for name in ['requirements', 'tags', 'preconditions', 'steps']:
            args = self.get_arguments(name)
            if len(args) == 0:
                args = getattr(cur_tc, name)
            setattr(new_tc, name, args)

        path = cur_tc.path
        self.repo.save(path, new_tc)
        self.redirect('/testcase/{:016x}'.format(int(id, 16)))


class TestCasesHandler(BaseHandler):
    def get(self):
        test_cases = self.repo.get()
        for t in test_cases:
            print(t.asdict())

        return self.render('testcases.html', test_cases=test_cases, heading_text='Test Cases')


class NewTestCaseHandler(BaseHandler):

    def get(self):
        return self.render('testcases-new.html',
                           directories=self.repo.get_categories(),
                           heading_text="Create Test Case")

    def post(self):
        try:
            directory = self.get_argument('location')
            if directory not in self.repo.get_categories():
                raise ValueError(f"'{directory}' does not exists")

            tc = self.repo.create(directory)

            self.redirect('/testcase/{:016x}'.format(tc.id))
        except ValueError as e:
            return self.render(f'404.html?{self.url_escape(str(e))}')


class Application(tornado.web.Application):
    is_closing = False

    def signal_handler(self, signum, frame):
        self.is_closing = True

    def try_exit(self):
        if self.is_closing:
            # clean up here
            tornado.ioloop.IOLoop.instance().stop()


def main():
    # TODO: Arguments
    if len(sys.argv) == 1:
        test_case_root = os.path.abspath('./test-cases')
    else:
        test_case_root = os.path.abspath(sys.argv[1])

    settings = {
        'static_path': os.path.join(os.path.dirname(__file__), 'static'),
        'template_path': os.path.join(os.path.dirname(__file__), 'templates'),
        'gzip': True,
        'debug': True,
        'default_handler_class': NotFoundHandler,
        'testcase_repo': TestCaseRepository(test_case_root, get_client_unique_id_generator())
    }

    application = Application([
        (r'/', HomeHandler),
        (r'/testcases/new', NewTestCaseHandler),
        (r'/testcases', TestCasesHandler),
        (r'/testcase/(.*)', TestCaseHandler)
    ], **settings)

    # See https://github.com/tornadoweb/tornado/issues/2804
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Patch MIME Types for Windows. This could be done in Windows globally
    # See: https://stackoverflow.com/questions/3442607/mime-types-in-the-windows-registry/3452261#3452261
    mimetypes.add_type('application/javascript', '.js')

    tornado.options.parse_command_line()
    signal.signal(signal.SIGINT, application.signal_handler)
    application.listen(8888)
    tornado.ioloop.PeriodicCallback(application.try_exit, 100).start()
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()
