from automationv3 import building_block, BlockResult, create_registry
import pytest


@pytest.fixture
def registry():
    return create_registry()


def test_simple_block_registration(registry):
    @building_block(registry=registry)
    def simple_block() -> BlockResult:
        return BlockResult(result=True)

    assert len(registry) == 1
    assert 'simple_block' in registry


def test_overwriting_blockname(registry):
    @building_block(name='simple_block_2', registry=registry)
    def simple_block() -> BlockResult:
        return BlockResult(result=True)

    assert len(registry) == 1
    assert 'simple_block_2' in registry


def test_cannot_have_non_default_kw_only(registry):
    with pytest.raises(ValueError):
        @building_block(registry=registry)
        def bad_block(*, nodefault) -> BlockResult:
            return BlockResult(result=True)


def test_block_args_must_resolve_to_token(registry):
    class NoTokenType:
        pass

    with pytest.raises(ValueError):
        @building_block(registry=registry)
        def bad_block(x: NoTokenType) -> BlockResult:
            return BlockResult(result=True)
