from typing import List, get_origin, get_args, Type, Union
from inspect import Parameter


class Token:
    def parse(self, args):
        return args[0], args[1:]


class StringToken(Token):
    def parse(self, args):
        if isinstance(args[0], str):
            return super().parse(args)
        else:
            return None, None


class NumberToken(Token):
    def parse(self, args):
        try:
            arg = float(args[0])
            return arg, args[1:]
        except:
            return None, None


class ListToken(Token):
    def __init__(self, container_token=None):
        self.container_token = container_token if container_token is not None else Token()

    def parse(self, args):
        # Right now this just eats token greedily until the container_token type
        # fails to parse a token. This means that if an argument is a List without
        # a container_token it will consume all arguments
        result = []
        while len(args) > 0:
            parsed, rest = self.container_token.parse(args)

            if parsed is None and rest is None:
                if len(result) > 0:
                    return result, args
                else:
                    return None, None
            else:
                result.append(parsed)
                args = rest

        if len(result) > 0:
            return result, args
        else:
            return None, None


# Default tokens that wrap python types
# int
# float
# str
std_tokens = {
    int: NumberToken,
    float: NumberToken,
    str: StringToken
}


def resolve_token_from_type(t: Type) -> Union[Token, None]:
    token = None

    if isinstance(t, type):
        if issubclass(t, Token):
            token = t()
        else:
            # Try our best to map to derived python types
            for clazz in std_tokens:
                if issubclass(t, clazz):
                    token = std_tokens[clazz]()
    else:
        # Generic Types
        if get_origin(t) == list:
            args = get_args(t)
            if len(args) == 1:
                token = ListToken(resolve_token_from_type(args[0]))
            else:
                token = ListToken()
    return token


def resolve_token(parameter: Parameter):
    annotation = parameter.annotation

    if annotation == Parameter.empty:
        if parameter.kind == Parameter.VAR_POSITIONAL:
            return ListToken()
        else:
            # TODO: Not sure what to do here. For now assume this is an error
            #       and return no token. I don't think it makes sense to attempt
            #       to coerce into some default type.
            return None
    else:
        return resolve_token_from_type(annotation)
