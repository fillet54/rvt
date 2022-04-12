
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
from collections import namedtuple
import sys
import asyncio
import os
import signal
import json
import mimetypes

import tornado.web
import tornado.websocket
import tornado.options
import tornado.httpserver
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from heroicons.jinja import heroicon_outline, heroicon_solid

import yaml
from yaml import safe_load, dump, Dumper
import os

from automationv3.util import get_client_unique_id_generator
from .framework import BlockResult, TestCase, default_registry, building_block
from .rvt_reader import LineInfo, ListNode, IncompleteListNode, SymbolNode, read_token, find_token, PushBackCharStream


class Icon(tornado.web.UIModule):
    def render(self, name: str, classnames='') -> str:
        return self.render_string(f'icons/{name.lower()}.svg', classnames=classnames)


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


class TemplateRendering:
    """
    A simple class to hold methods for rendering templates.
    """

    def render_template(self, template_name, **kwargs):
        template_dirs = []
        if self.settings.get('template_path', ''):
            template_dirs.append(
                self.settings["template_path"]
            )

        env = Environment(loader=FileSystemLoader(template_dirs))

        # Add heroicons
        env.globals.update(
            {
                "heroicon_outline": heroicon_outline,
                "heroicon_solid": heroicon_solid,
            }
        )

        try:
            template = env.get_template(template_name)
        except TemplateNotFound:
            raise TemplateNotFound(template_name)
        content = template.render(kwargs)
        return content

NavItem = namedtuple('NavItem', ['display', 'path', 'icon'])

# pylint: disable=W0223
class BaseHandler(tornado.web.RequestHandler, TemplateRendering):
    """
    RequestHandler already has a `render()` method. I'm writing another
    method `render2()` and keeping the API almost same.
    """

    @property
    def repo(self) -> TestCaseRepository:
        return self.settings['testcase_repo']

    def render2(self, template_name, **kwargs):
        """
        This is for making some extra context variables available to
        the template
        """
        kwargs.update({
            'settings': self.settings,
            'STATIC_URL': self.settings.get('static_url_prefix', '/static/'),
            'static_url': self.static_url,
            'request': self.request,
            'xsrf_token': self.xsrf_token,
            'xsrf_form_html': self.xsrf_form_html,
            'json': json,
            'navitems': self.settings.get('navitems', [])
        })
        content = self.render_template(template_name, **kwargs)
        self.write(content)


class NotFoundHandler(BaseHandler):
    def get(self):
        return self.render2('404.html')


class HomeHandler(BaseHandler):
    def get(self):
        return self.render2('home.html', heading_text='Dashboard')


class TestCaseHandler(BaseHandler):
    def get(self, id):
        testcase = self.repo.get(id=int(id, 16))
        return self.render2('testcase.html', testcase=testcase)

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

        return self.render2('testcases.html', test_cases=test_cases, heading_text='Test Cases')


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


class AutocompleteHandler(BaseHandler):
    def set_default_headers(self):
        self.set_header("Content-Type", 'application/json')

    def get(self):
        text = self.get_argument('text', '')
        line = int(self.get_argument('line', 0))
        col = int(self.get_argument('col', 0))

        tokens, errors = read_token(PushBackCharStream(text))
        block_names = default_registry.keys()

        completions = []
        if len(tokens) == 0:
            completions += block_names
            from_loc = to_loc = LineInfo(0, 0)
        else:
            target = find_token(tokens, line, col, level=1)

            if target is not None and isinstance(tokens[0], SymbolNode):
                from_loc = target.info.start
                to_loc = target.info.end

                # Block name autocomplete
                if target == tokens[0]:
                    completions += [
                        name for name in block_names if name.startswith(target)]
                else:
                    # need to resolve block determine block token and then
                    # ask token to autocomplete
                    partial_args = []
                    for token in tokens:
                        partial_args.append(token)
                        if token == target:
                            break
                    # TODO: Finish this
                    #block_name = partial_args[0]
                    #args = partial_args[1:]
                    # blocks = find_blocks_partial(block_name, args)
                    # for block in blocks:
                    #    completions += block.tokens[len(args)-1].autocomplete(args[-1])
            else:
                # Autocomplete cannot be completed leading token is not a symbol
                from_loc = to_loc = LineInfo(line, col)
                pass

        if len(completions) > 0:
            self.write(json.dumps({
                'list': completions,
                'from': from_loc,
                'to': to_loc
            }))
        else:
            # argument autocomplete
            self.write(json.dumps({'list': []}))


class Application(tornado.web.Application):
    is_closing = False

    def signal_handler(self, signum, frame):
        self.is_closing = True

    def try_exit(self):
        if self.is_closing:
            # clean up here
            tornado.ioloop.IOLoop.instance().stop()

# A few building blocks for autocomplete testing. Can be removed at some point


@building_block
def VerifyAccept():
    return BlockResult(result=True)


@building_block
def VerifyReturn():
    return BlockResult(result=True)


@building_block
def VerifyTimeout():
    return BlockResult(result=True)


@building_block
def Test():
    return BlockResult(result=True)


@building_block
def Wait():
    return BlockResult(result=True)
# End test building blocks


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
        'testcase_repo': TestCaseRepository(test_case_root, get_client_unique_id_generator()),
        'ui_modules': {'Icon': Icon},
        'navitems': [
            NavItem('Dashboard', '/', 'home'),
            NavItem('Test Cases', '/testcases', 'collection'),
            NavItem('Snippets', '/snippets', 'document-text'),
            NavItem('Requirements', '/requirements', 'clipboard-list'),
            NavItem('Reports', '/reports', 'chart-bar')
        ]
    }

    application = Application([
        (r'/', HomeHandler),
        (r'/testcases/new', NewTestCaseHandler),
        (r'/testcases', TestCasesHandler),
        (r'/testcase/(.*)', TestCaseHandler),
        (r'/api/autocomplete', AutocompleteHandler)
    ], **settings)

    # See https://github.com/tornadoweb/tornado/issues/2804
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # Patch MIME Types for Windows. This could be done in Windows globally
    # See: https://stackoverflow.com/questions/3442607/mime-types-in-the-windows-registry/3452261#3452261
    mimetypes.add_type('application/javascript', '.js')

    port = 8087
    print(f"Starting Automation-V3 Framework on port {port}")

    tornado.options.parse_command_line()
    signal.signal(signal.SIGINT, application.signal_handler)
    application.listen(port)
    tornado.ioloop.PeriodicCallback(application.try_exit, 100).start()
    tornado.ioloop.IOLoop.instance().start()


if __name__ == "__main__":
    main()
