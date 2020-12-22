from automationv3.rvt_reader import PushBackCharStream


def test_PushBackCharStream_as_iterator():
    inchars = "abcd\n12345"
    iterator = PushBackCharStream(inchars)

    chars = [c for c in iterator]

    assert chars[0] == 'a'
    assert chars[0].line == 0
    assert chars[0].col == 0

    assert chars[4] == '\n'
    assert chars[4].line == 0
    assert chars[4].col == 4

    assert chars[5] == '1'
    assert chars[5].line == 1
    assert chars[5].col == 0


def test_PushBackCharStream_simple_pushback():
    inchars = "abcd\n12345"
    iterator = PushBackCharStream(inchars)

    char = next(iterator)
    iterator.push_back(char)
    char2 = next(iterator)

    assert char2 == 'a'
    assert char2.line == 0
    assert char2.col == 0


def test_PushBackCharStream_line_pushback():
    inchars = "abcd\n12"
    iterator = PushBackCharStream(inchars)

    chars = [c for c in iterator]

    iterator.push_back(chars[-1])
    iterator.push_back(chars[-2])
    iterator.push_back(chars[-3])

    char1 = next(iterator)
    char2 = next(iterator)
    char3 = next(iterator)

    assert char1 == '\n'
    assert char1.line == 0
    assert char1.col == 4

    assert char2 == '1'
    assert char2.line == 1
    assert char2.col == 0

    assert char3 == '2'
    assert char3.line == 1
    assert char3.col == 1
