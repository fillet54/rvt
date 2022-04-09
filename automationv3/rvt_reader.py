# Rvt Language Parser
from typing import Iterator, List, Union
from collections import namedtuple

reprLevel = 0

LineInfo = namedtuple('LineInfo', ['line', 'col'])
LineRange = namedtuple('LineRange', ['start', 'end'])


class Character(str):
    def __new__(cls, val, *args, **kwargs):
        return super().__new__(cls, val)

    def __init__(self, val, line: int, col: int):
        self.line = line
        self.col = col

    @property
    def lineinfo(self):
        return LineInfo(self.line, self.col)


class PushBackCharStream:
    def __init__(self, chars: Union[str, Iterator[str]]):
        if isinstance(chars, str):
            self.iterator = iter(chars)
        else:
            self.iterator = chars

        self.pushed_back: List[str] = []

        self.line = 0
        self.col = 0

        self.line_history: List[int] = [0]

        self.eof_info = LineInfo(0, 0)

        self.__reached_end = False

    def __iter__(self):
        return self

    def __next__(self):
        if self.pushed_back:
            char = self.pushed_back.pop()
        else:
            try:
                char = next(self.iterator)
            except StopIteration:
                self.__reached_end = True
                raise

            self.eof_info = LineInfo(self.line, self.col)
        char = Character(char, self.line, self.col)

        # advanced character position
        if char == '\n':
            self.line += 1
            self.col = 0
        else:
            self.col += 1

        # Save last line history for pushback
        if len(self.line_history) <= self.line:
            self.line_history.append(0)
        self.line_history[self.line] = self.col

        return char

    def push_back(self, char: str):
        self.pushed_back.append(char)

        # Reverse the position
        if self.col == 0:
            self.line -= 1
            self.col = self.line_history[self.line]
        else:
            self.col -= 1

    @property
    def empty(self):
        return len(self.pushed_back) == 0 and self.__reached_end


class EOF:
    pass


def info_location_str(info):
    start = f"{info.start.line}:{info.start.col}"
    end = f"{info.end.line}:{info.end.col}"
    return f"@{start}-{end}"


class SymbolNode(str):
    def __new__(cls, val, *args, **kwargs):
        return super().__new__(cls, val)

    def __init__(self, val, namespace=None):
        self.namespace = namespace

    def __repr__(self):
        if hasattr(self, 'info'):
            return f"<{self.__class__.__name__}: '{str(self)}' {info_location_str(self.info)}>"
        return f"<{self.__class__.__name__}: '{str(self)}>"


class KeywordNode(SymbolNode):
    pass


class ListNode(list):
    def __repr__(self):
        lines = [f'<{self.__class__.__name__}:']
        global reprLevel
        leading = " " * (reprLevel * 2)
        reprLevel += 1
        for val in self:
            lines.append(f'{leading}- {repr(val)}')
        reprLevel -= 1
        lines.append(f'@{info_location_str(self.info)}>')
        return '\n'.join(lines)


class IncompleteListNode(ListNode):
    pass


class VectorNode(ListNode):
    pass


class IncompleteVectorNode(VectorNode):
    pass


class MapNode(dict):
    pass


class IncompleteMapNode(MapNode):
    pass


class StringNode(str):
    def __repr__(self):
        if hasattr(self, 'info'):
            return f"<{self.__class__.__name__}: '{str(self)}' {info_location_str(self.info)}>"
        return f"<{self.__class__.__name__}: '{str(self)}>"


class IncompleteStringNode(StringNode):
    pass


class ErrorNode(str):
    pass


# TODO: Unicode escapes
str_escapes = {
    'n': lambda stream: ('\n', []),
    'r': lambda stream: ('\r', []),
}


def read_str(stream: Iterator[Character]):
    chars = []
    errors = []

    # quote
    startch = next(stream)

    for ch in stream:
        if ch == startch:
            string = StringNode(''.join(chars))
            string.info = LineRange(startch.lineinfo, ch.lineinfo)
            return string, []
        elif ch == '\\':
            # escape
            # read next char
            escch = next(stream)
            if escch in str_escapes:
                chars.append(str_escapes[escch](stream))
            elif escch == startch:
                chars.append(escch)
            else:
                error = ErrorNode("Invalid escape sequence '\\{escch}'")
                error.info = LineRange(ch.lineinfo, escch.lineinfo)
                errors.append(error)
                chars.append(escch)
        else:
            chars.append(ch)

    # end of stream
    incomplete = IncompleteStringNode(''.join(chars))
    incomplete.info = LineRange(startch.lineinfo, stream.eof_info)
    errors.append(incomplete)

    return incomplete, errors


def read_map(stream):
    pass


def read_set(stream):
    pass


list_endchars = {
    ')': '(',
    ']': '['
}


def read_list(stream: Iterator[Character], endchar=')'):
    vals = ListNode()
    errors = []

    startch = next(stream)

    for ch in stream:
        if ch == endchar:
            vals.info = LineRange(startch.lineinfo, ch.lineinfo)
            return vals, errors
        elif ch in whitespace or ch == ',':
            # whitespace
            pass
        elif ch == ')' or ch == ']':
            stream.push_back(ch)
            error = ErrorNode(f"Unexpected character '{ch}'")
            error.info = LineRange(startch.lineinfo, ch.lineinfo)
            errors.append(errors)
            incomplete = IncompleteListNode(vals)
            incomplete.info = error.info
            return incomplete, errors
        else:
            stream.push_back(ch)
            token, errs, = read_token(stream)
            vals.append(token)
            errors += errs

    # we exhausted characters before getting terminating character
    # so this is an error but we can provide an incomplete list
    incomplete = IncompleteListNode(vals)
    incomplete.info = LineRange(startch.lineinfo, stream.eof_info)
    errors.append(incomplete)

    return incomplete, errors


def read_vector(stream):
    l, errors = read_list(stream, endchar=']')

    if isinstance(l, IncompleteListNode):
        v = IncompleteVectorNode(l)
        errors = errors[:-1]
        errors.append(v)
    else:
        v = VectorNode(l)

    v.info = l.info
    return v, errors


# TODO: Probably want to turn this into valid characters
nonsymbol_tokens = set([';', ']', '[', ')', '(', '#', ',', '"', "'"])

whitespace = set([' ', '\t', '\r', '\n', ','])


def read_symbol(stream: Iterator[Character]):
    chars = []
    startch = endch = None
    eof = True

    for ch in stream:
        if startch is None:
            startch = endch = ch

        if not ch in whitespace and ch not in nonsymbol_tokens:
            chars.append(ch)
            endch = ch
        elif ch in whitespace or ch in nonsymbol_tokens:
            stream.push_back(ch)
            eof = False
            break
        else:
            # Error
            error = ErrorNode(f"Illegal character for symbol '{ch}'")
            error.info = LineRange(startch.lineinfo, ch.lineinfo)
            # TODO: Scan until whitespace, ), }, or ]
            return error, [error]

    # Either space encountered or EOF
    symbol = SymbolNode(''.join(chars))
    if eof:
        symbol.info = LineRange(startch.lineinfo, stream.eof_info)
    else:
        symbol.info = LineRange(startch.lineinfo, endch.lineinfo)

    return symbol, []


def read_comment(stream):
    pass


def read_keyword(stream):
    symbol, errors = read_symbol(stream)
    keyword = KeywordNode(symbol[1:])
    keyword.info = symbol.info
    return keyword, errors


dispatch = {
    '(': read_list,
    '[': read_vector,
    '{': read_map,
    '#': read_set,
    ':': read_keyword,
    ';': read_comment,
    '"': read_str,
    "'": read_str
}


def read_token(stream: PushBackCharStream):

    for ch in stream:
        if not ch in whitespace:
            stream.push_back(ch)
            return dispatch.get(ch, read_symbol)(stream)


def compare_range(val, start, end):
    if val < start:
        return -1
    elif val > end:
        return 1
    else:
        return 0


def in_line_range(tree, line, col):
    start, end = tree.info
    if start.line == end.line and line == start.line:
        return compare_range(col, start.col, end.col)
    elif start.line == line:
        return compare_range(col, start.col, col)
    elif end.line == line:
        return compare_range(col, col, end.col)
    else:
        return compare_range(line, start.line, end.line)


def find_token(tree, line, col, level=-1):
    if in_line_range(tree, line, col) == 0:
        if level == 0:
            return tree

        next_level = level - 1 if level != -1 else -1

        if isinstance(tree, (ListNode, IncompleteListNode)):
            for child in tree:
                child.parent = tree
                token = find_token(child, line, col, next_level)
                if token is not None:
                    return token
        else:
            return tree
    else:

        # Trailing whitespace goes to previous token
        return None


def read(s):
    stream = PushBackCharStream(s)
    token, errors = read_token(stream)

    if not stream.empty:
        errors.append("NOT EMPTY")
    return token, errors


if __name__ == '__main__':

    program = '   ,,,,  (     mySymbol, another.symbol.afda.adfa, \n(:keyword)'
    stream = PushBackCharStream(program)

    token, errors = read_token(stream)
    print(repr(token))

    #token2 = find_token(token, 0, 18)
    #parent = token2.parent
    # print(repr(token2))
    # print(repr(parent))
