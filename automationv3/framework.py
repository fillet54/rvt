from collections import defaultdict
from typing import Callable, DefaultDict, Dict, List, Optional, Union, Any, Tuple, get_origin
import shlex
from inspect import signature, Parameter
from .tokens import resolve_token
from functools import partial
from enum import Enum
import copy

import yaml
from yaml import safe_load, dump, Dumper

# YAML helpers


class HexInt(int):
    pass


class BlockStr(str):
    pass


def hex_representer(dumper, data):
    return yaml.ScalarNode('tag:yaml.org,2002:int', '0x{:016X}'.format(data))


def str_presenter(dumper, data):
    linedata = data.splitlines()
    try:
        dlen = len(linedata)
        if (dlen > 1):
            return dumper.represent_scalar('tag:yaml.org,2002:str', "\n".join(linedata), style='|')
    except TypeError as ex:
        print("ERROR")
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


yaml.add_representer(HexInt, hex_representer)
yaml.add_representer(BlockStr, str_presenter)

# Signature helpers


def get_nondefault_keyword_only_parameters(func):
    sig = signature(func)
    params = [sig.parameters[name] for name in sig.parameters]
    return [p for p in params if p.kind == Parameter.KEYWORD_ONLY and p.default == Parameter.empty]


def get_positional_parameters(func):
    POSITIONAL = [Parameter.POSITIONAL_ONLY,
                  Parameter.POSITIONAL_OR_KEYWORD,
                  Parameter.VAR_POSITIONAL]
    sig = signature(func)
    params = [sig.parameters[name] for name in sig.parameters]
    return [p for p in params if p.kind in POSITIONAL]


class DerivedTag(str):
    pass


class TestCase:
    def __init__(self, id, preconditions=[], steps=[], requirements=[], description='', tags=[], path=None):
        self.id = id
        self.steps = steps
        self.preconditions = preconditions
        self.description = description
        self.requirements = requirements
        self.tags = tags
        self.path = path

    def derive(self, tag):
        tc_copy = copy.copy(self)
        tc_copy.tags = tc_copy.tags.copy()
        tc_copy.tags.append(DerivedTag(tag))
        return tc_copy

    def asdict(self):
        return dict(
            id=HexInt(self.id),
            description=self.description,
            requirements=self.requirements,
            tags=self.tags,
            preconditions=[BlockStr(s) for s in self.preconditions],
            steps=[BlockStr(s) for s in self.steps])

    @staticmethod
    def load(stream):
        if isinstance(stream, dict):
            data = stream
        else:
            data = safe_load(stream)

        return TestCase(
            id=data.get('id'),
            preconditions=data.get('preconditions', []),
            steps=data.get('steps', []),
            description=data.get('description', ''),
            requirements=data.get('requirements', []),
            tags=data.get('tags', []))

    def dump(self, stream=None):
        return dump(self.asdict(), stream, Dumper=Dumper, sort_keys=False)


class Result(Enum):
    PASSED = 1,
    FAILED = 2,
    NOT_RUN = 3

    def __str__(self):
        return super().__str__().split('.')[-1]


class BlockResult:
    def __init__(self: 'BlockResult',
                 result: Result,
                 output: Optional[str] = None,
                 cleanup: Optional[Callable[[], bool]] = None):

        self.result = result
        self.output = output
        self.cleanup = cleanup

    def run_cleanup(self: 'BlockResult'):
        if self.cleanup is not None:
            try:
                return self.cleanup()
            except:
                return False
        else:
            return True

    def __str__(self):
        return str(self.result)


class SetupBlockResult(BlockResult):
    ''' This class is used for blocks that only should be cleaned up at 
        then end of all tests. This is used to facilitate setup'''
    pass


class BlockType(Enum):
    BUILDING = 1
    SETUP = 2


BuildingBlock = Callable[..., BlockResult]
SetupBlock = Callable[..., List]


def create_registry():
    return defaultdict(list)


default_registry = create_registry()


def validate_block(func):
    if len(get_nondefault_keyword_only_parameters(func)) != 0:
        raise ValueError(
            "Building Block cannot have non-defaulted keyword only parameters")


def validate_setup_block(func):
    # First argument of a setup block is always a list of raw blocks
    positional_args = get_positional_parameters(func)
    if len(positional_args) == 0:
        raise ValueError("Setup Block must take a list as first argument")
    try:
        if get_origin(positional_args[0].annotation) == list:
            raise ValueError("Setup Block must take a list as first argument")
    except:
        raise ValueError("Setup Block must take a list as first argument")


def annotate_tokens(func):
    positional = get_positional_parameters(func)
    tokens = []
    for param in positional:
        token = resolve_token(param)
        if token is None:
            raise ValueError(
                f'Block {func.__name__} could not resolve Token Type for {param.name}')
        tokens.append(token)
    func.tokens = tokens


def building_block(func=None, *, name: Optional[str] = None, registry=default_registry):
    def inner(func: BuildingBlock):
        validate_block(func)
        annotate_tokens(func)
        block_name = name if name is not None else func.__name__
        registry[block_name].append((BlockType.BUILDING, func))
        return func
    # Handles the no argument case
    if callable(func):
        return inner(func)
    return inner


def setup_block(func=None, *, name: Optional[str] = None, registry=default_registry):
    def inner(func: SetupBlock):
        validate_block(func)
        validate_setup_block(func)
        annotate_tokens(func)
        block_name = name if name is not None else func.__name__
        registry[block_name].append((BlockType.SETUP, func))
        return func
    # Handles the no argument case
    if callable(func):
        return inner(func)
    return inner


def scan_for_blocks(namespace: str):
    """ Scans the namespace for modules and imports them to register blocks """

    import importlib
    import pkgutil

    name = importlib.util.resolve_name(namespace, package=__package__)
    spec = importlib.util.find_spec(name)

    if spec is not None:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_modue(module)

        for finder, name, _ in pkgutil.iter_modules(module._path__):
            spec = finder.find_spec(name)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)


def bind_args(block, args):
    parsed_args = []
    for token in block.tokens:
        # Ran out of arguments
        if len(args) == 0:
            return None

        parsed, rest = token.parse(args)
        if parsed is not None and rest is not None:
            parsed_args.append(parsed)
        else:
            return None
        args = rest

    # All arguments must be consume for a bind to occur
    if len(args) > 0:
        return None
    else:
        return partial(block, *parsed_args)


def get_block(name: str,
              args: Optional[List[Any]] = None,
              *,
              env={},
              registry=default_registry) -> Tuple[BlockType, BlockResult]:

    for block_type, block in registry[name]:
        bounded_block = bind_args(block, args)
        if bounded_block is not None:
            return block_type, bounded_block

    return None, None


def shlex_parser(line):
    parts = shlex.split(line)
    return parts[0], parts[1:]


def expand_setup(setup, steps):
    while len(setup) > 0:
        cur = setup.pop(0)
        new_steps = []
        for expanded in cur(steps):
            new_steps.append(expanded)
        steps = new_steps
    return steps


def simple_runner(lines):
    parsed = [shlex_parser(line) for line in lines.split('\n')]

    # First we need to resolve the blocks and sort setup vs other
    setup = []
    other = []
    for name, args in parsed:
        block_type, block = get_block(name, args)

        if block_type is None:
            print(f'Could not find block for {name}')
        elif block_type is BlockType.SETUP:
            setup.append(block)
        else:
            # Don't keep the bounded blocks as setup blocks can
            # modify
            other.append((name, args))

    # Expand the test case based on the setup blocks. Note that a setup
    # block may expand a single test case into multiple derived tests
    derived_test_cases = expand_setup(setup, (other,))

    # Run the blocks and keep track for clean up
    run: List[BlockResult] = []
    for name, args in other:
        block_type, block = get_block(name, args)

        if block_type is None:
            print(f'Could not find block for {name}')
        elif block_type is BlockType.BUILDING:
            result = block()
            print(result)
            run.append(result)
        else:
            print(f'Unexpected block type for {name}')

    # Cleanup the test
    # It is not clear what should or shouldnt be cleaned up. I suspect that
    # it might make sense to sometimes clean up and other times not. In
    # all cases preconditions should
    for result in reversed(run):
        if isinstance(result, SetupBlockResult):
            # Keep for end of test cleanup
            pass
        else:
            result.run_cleanup()


def queue_text_test_case():
    pass
