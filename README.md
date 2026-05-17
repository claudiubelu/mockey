# mockey

[![Release](https://img.shields.io/github/v/release/claudiubelu/mockey)](https://img.shields.io/github/v/release/claudiubelu/mockey)
[![Build status](https://img.shields.io/github/actions/workflow/status/claudiubelu/mockey/main.yml?branch=main)](https://github.com/claudiubelu/mockey/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/claudiubelu/mockey/branch/main/graph/badge.svg)](https://codecov.io/gh/claudiubelu/mockey)
[![Commit activity](https://img.shields.io/github/commit-activity/m/claudiubelu/mockey)](https://img.shields.io/github/commit-activity/m/claudiubelu/mockey)
[![License](https://img.shields.io/github/license/claudiubelu/mockey)](https://img.shields.io/github/license/claudiubelu/mockey)

A fixture that enforces correct `mock.patch` autospec behaviour, surfacing signature violations that the standard mock library silently ignores.

- **Github repository**: <https://github.com/claudiubelu/mockey/>
- **Documentation**: <https://claudiubelu.github.io/mockey/>

---

## Background and motivation

This library is based on
[oslotest's `mock_fixture.py`](https://github.com/openstack/oslotest/blob/0b348bccd3639b6d2a8acd19e62b1dd19ad903d6/oslotest/mock_fixture.py),
extracted and extended as a standalone package.

The standard `unittest.mock` library has long-standing bugs that let mocked methods be called with the
wrong number or names of arguments without raising a `TypeError`. Tests pass, but they are not testing
anything meaningful, the real code would raise immediately if called the same way.

There are multiple root causes, some of which have been reported in upstream issues:

- [mock#393](https://github.com/testing-cabal/mock/issues/393): `mock.Mock` and `mock.MagicMock`
  have no `autospec=` parameter; using `spec=` only checks attribute *existence*, not call signatures.
- [mock#396](https://github.com/testing-cabal/mock/issues/396): `mock.patch` with `autospec=True`
  does not consume the implicit `self` argument on instance methods, causing every patched-method
  call to fail the signature check (so people turn `autospec` off).

## What this library fixes

| Issue | Without mockey | With mockey |
|---|---|---|
| `mock.Mock(autospec=MyClass)` - calls with wrong args | silently accepted | `TypeError` raised |
| `mock.Mock(autospec=MyClass)` - non-existent attribute | silently created | `AttributeError` raised |
| `mock.patch.*` - calls with wrong args | silently accepted | `TypeError` raised |
| `mock.patch.*` - no explicit `autospec=True` needed | must opt in per-patch | enforced globally |
| Return value of `def get_foo(self) -> Foo` (via `mock.Mock(autospec=…)`) | plain `MagicMock` | autospecced as `Foo` |
| Return value of `def get_foo(self) -> Foo` (via `mock.patch.object(…)`) | plain `MagicMock` | autospecced as `Foo` |
| Return value of `def get_none(self) -> None` | `MagicMock` object | `None` |
| Constructor: `mock.Mock(autospec=MyClass)(wrong_args)` | silently accepted | `TypeError` raised |
| Patching an already-mocked attribute | silently double-patches | `InvalidSpecError` raised |

## What this library adds compared to oslotest

In addition to what `oslotest`'s `mock_fixture` fixes, this library adds on top of that:

- **Return-value autospeccing from type hints**: if a method declares `-> SomeClass`, its mock
  return value is automatically autospecced as `SomeClass`, so chained calls are also checked.
- **`-> None` enforcement**: methods annotated `-> None` return actual `None`, matching runtime
  behaviour and preventing tests from accidentally asserting on a `MagicMock` return value.
- **Constructor signature enforcement**: calling `mock.Mock(autospec=MyClass)(wrong_args)` raises
  `TypeError`, just as calling the real class' constructor would.

---

## Installation

```bash
pip install mockey
```

## Usage

### Critical: import order

`patch_mock_module()` must be called **before any test module is imported**. The reason is that
`@mock.patch` decorators (including `mock.patch.object` and `mock.patch.multiple`) capture
`mock._patch` at *class definition time*, not at call time. If `patch_mock_module()` is called
after the test class is imported, those decorators will use the original, unfixed `mock._patch`
and signature enforcement will silently not apply.

The canonical place is your test package's `__init__.py`:

```python
# tests/__init__.py
from mockey.fixture import patch_mock_module

patch_mock_module()
```

This file is imported by Python before any test module in the `tests/` package, so all
`@mock.patch` decorators in all test files pick up the patched version automatically.

### MockAutospecFixture

Activate `MockAutospecFixture` in your test's `setUp`. With `testtools`:

```python
from mockey import MockAutospecFixture
import testtools

class MyTestCase(testtools.TestCase):
    def setUp(self):
        super().setUp()
        self.useFixture(MockAutospecFixture())
```

With plain `unittest`:

```python
from mockey import MockAutospecFixture
import unittest

class MyTestCase(unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._fixture = MockAutospecFixture()
        self._fixture.setUp()
        self.addCleanup(self._fixture.cleanUp)
```

### Using `mock.Mock(autospec=...)`

Once the fixture is active, pass `autospec=` directly to `mock.Mock` or `mock.MagicMock`:

```python
from unittest import mock
from mymodule import MyService, MyModel

# Autospec from a class - attribute access and call signatures are enforced.
m = mock.Mock(autospec=MyService)

# Correct call - passes.
m.do_something(user_id=42)

# Wrong signature - raises TypeError, just like the real class would.
m.do_something(unknown_kwarg="oops")   # TypeError

# Non-existent attribute - raises AttributeError.
m.typo_metod  # AttributeError

# Autospec from an instance works the same way.
service = MyService()
m2 = mock.Mock(autospec=service)
```

### Return-value autospeccing

If a method declares a concrete return type, calling it on an autospecced mock returns an
autospecced instance of that type - no extra setup required:

```python
class Repository:
    def get_user(self, user_id: int) -> User:
        ...

m = mock.Mock(autospec=Repository)
user_mock = m().get_user(1)

# user_mock is autospecced as User - wrong attribute access raises AttributeError.
user_mock.nonexistent_field  # AttributeError

# Methods on user_mock also enforce signatures.
user_mock.update(name="Alice")  # passes if that matches User.update's signature
```

Methods returning `None` behave correctly too:

```python
class Writer:
    def flush(self) -> None:
        ...

m = mock.Mock(autospec=Writer)
result = m().flush()
assert result is None
```

### Using `mock.patch` (decorator and context manager)

With `patch_mock_module()` active, `autospec=True` is the default for all patches - you do not
need to write it yourself, or update your existing unit tests:

```python
# Both of these enforce signature checking on Foo.bar.
with mock.patch.object(Foo, "bar"):
    ...

@mock.patch.object(Foo, "bar")
def test_something(self, mock_bar):
    ...
```

To opt out of autospeccing for a specific patch, pass `autospec=False` explicitly:

```python
with mock.patch.object(Foo, "bar", autospec=False):
    Foo().bar()   # no signature checking
```

Passing `new=`, `new_callable=`, `create=`, or `spec=` also disables auto-injection, matching
the standard library's semantics.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to set up the development environment, run the
linter (`make check`), and run the test suite (`make test`).
