from automationv3.tokens import StringToken
from typing import List
from inspect import Parameter
from automationv3 import Token, resolve_token, NumberToken, resolve_token_from_type, ListToken


def test_resolve_token_type():
    param = Parameter('x', Parameter.POSITIONAL_ONLY, annotation=Token)
    token = resolve_token(param)

    assert isinstance(token, Token)


def test_resolve_int():
    param = Parameter('x', Parameter.POSITIONAL_ONLY, annotation=int)
    token = resolve_token(param)

    assert isinstance(token, NumberToken)


def test_resolve_float():
    param = Parameter('x', Parameter.POSITIONAL_ONLY, annotation=float)
    token = resolve_token(param)

    assert isinstance(token, NumberToken)


def test_resolve_variable_positional():
    param = Parameter('x', Parameter.VAR_POSITIONAL)
    token = resolve_token(param)

    assert isinstance(token, ListToken)


def test_resolve_generic_list():
    param = Parameter('x', Parameter.VAR_POSITIONAL, annotation=List)
    token = resolve_token(param)

    assert isinstance(token, ListToken)
    assert isinstance(token.container_token, Token)


def test_resolve_specific_list():
    param = Parameter('x', Parameter.VAR_POSITIONAL, annotation=List[str])
    token = resolve_token(param)

    assert isinstance(token, ListToken)
    assert isinstance(token.container_token, StringToken)


def test_string_token():
    args = ["first", "second"]

    arg, rest = StringToken().parse(args)

    assert arg == 'first'
    assert rest == args[1:]


def test_string_token_failure():
    args = [1, "second"]

    arg, rest = StringToken().parse(args)

    assert arg is None


def test_number_token_for_int():
    args = ["123", "second"]

    arg, rest = NumberToken().parse(args)

    assert arg == 123
    assert rest == args[1:]


def test_number_token_for_float():
    args = ["123.123", "second"]

    arg, rest = NumberToken().parse(args)

    assert arg == 123.123
    assert rest == args[1:]


def test_list_token_generic():
    args = ["123", 3443, "abc"]

    arg, rest = ListToken().parse(args)

    assert arg == args
    assert len(rest) == 0


def test_list_token_specific():
    args = [123, 3443, "abc"]

    arg, rest = ListToken(container_token=NumberToken()).parse(args)

    assert arg == args[:2]
    assert len(rest) == 1
